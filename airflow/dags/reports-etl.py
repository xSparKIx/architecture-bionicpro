from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.operators.python import PythonOperator
from airflow_clickhouse_plugin.hooks.clickhouse import ClickHouseHook
# from airflow_clickhouse_plugin.operators.clickhouse import ClickHouseOperator

from airflow.operators.empty import EmptyOperator

import pandas as pd

# -------------------------------------------------------------------
# Параметры DAG
# -------------------------------------------------------------------
default_args = {
    'owner': 'bionicpro',
    'depends_on_past': False,
    'start_date': datetime(2025, 1, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'etl_user_analytics',
    default_args=default_args,
    description='ETL для витрины пользовательской аналитики',
    schedule='0 1 * * *',          # для Airflow 3.x (вместо schedule_interval)
    catchup=False,
    tags=['etl', 'reports'],
)

# -------------------------------------------------------------------
# 1. Создание таблицы витрины (если не существует)
# -------------------------------------------------------------------
# create_table_sql = """
# CREATE TABLE IF NOT EXISTS user_analytics
# (
#     user_id          String,
#     username         String,
#     full_name        String,
#     email            String,
#     prosthetic_id    String,
#     total_sessions   UInt32,
#     total_duration   UInt32,
#     avg_response_ms  Float32,
#     last_active      DateTime,
#     report_date      Date
# ) ENGINE = MergeTree()
# ORDER BY (report_date, user_id)
# """

def create_table_if_not_exists(**context):
    ch_hook = ClickHouseHook(clickhouse_conn_id='clickhouse_db')
    sql = """
    CREATE TABLE IF NOT EXISTS user_analytics
    (
        user_id          String,
        username         String,
        full_name        String,
        email            String,
        prosthetic_id    String,
        total_sessions   UInt32,
        total_duration   UInt32,
        avg_response_ms  Float32,
        last_active      DateTime,
        report_date      Date
    ) ENGINE = MergeTree()
    ORDER BY (report_date, user_id)
    """
    ch_hook.execute(sql)

create_table = PythonOperator(
    task_id='create_table',
    python_callable=create_table_if_not_exists,
    dag=dag,
)

# -------------------------------------------------------------------
# 2. Extract: данные из CRM
# -------------------------------------------------------------------
def extract_crm(**context):
    pg_hook = PostgresHook(postgres_conn_id='crm_db')
    # Инкрементальная загрузка по updated_at
    # Для простоты пока берём все записи (можно заменить на последнюю дату)
    sql = """
        SELECT user_id, username, full_name, email, prosthetic_id, created_at
        FROM customers
    """
    df = pg_hook.get_pandas_df(sql)
    # Сохраняем в XCom
    context['task_instance'].xcom_push(key='crm_data', value=df.to_json())
    return df.shape[0]

# -------------------------------------------------------------------
# 3. Extract: агрегированная телеметрия за последние сутки
# -------------------------------------------------------------------
def extract_telemetry_agg(**context):
    pg_hook = PostgresHook(postgres_conn_id='telemetry_db')
    sql = """
        SELECT user_id,
               COUNT(DISTINCT session_id) AS total_sessions,
               SUM(duration_seconds) AS total_duration,
               AVG(response_time_ms) AS avg_response_ms,
               MAX(event_time) AS last_active
        FROM telemetry
        WHERE event_time > NOW() - INTERVAL '1 day'
        GROUP BY user_id
    """
    df = pg_hook.get_pandas_df(sql)
    context['task_instance'].xcom_push(key='telemetry_agg', value=df.to_json())
    return df.shape[0]

# -------------------------------------------------------------------
# 4. Transform: объединение и расчёт метрик
# -------------------------------------------------------------------
def transform_and_join(**context):
    crm_json = context['task_instance'].xcom_pull(key='crm_data', task_ids='extract_crm')
    tele_json = context['task_instance'].xcom_pull(key='telemetry_agg', task_ids='extract_telemetry_agg')
    if not crm_json or not tele_json:
        raise ValueError("Нет данных для объединения")

    df_crm = pd.read_json(crm_json)
    df_tele = pd.read_json(tele_json)

    # Объединение по user_id
    df_result = pd.merge(df_crm, df_tele, on='user_id', how='outer')
    # Заполняем пропуски
    df_result.fillna({'total_sessions': 0, 'total_duration': 0, 'avg_response_ms': 0}, inplace=True)
    df_result['report_date'] = datetime.now().date()

    # Приводим типы для ClickHouse
    df_result['total_sessions'] = df_result['total_sessions'].astype('int32')
    df_result['total_duration'] = df_result['total_duration'].astype('int32')
    df_result['avg_response_ms'] = df_result['avg_response_ms'].astype('float32')

    context['task_instance'].xcom_push(key='result_data', value=df_result.to_json())
    return df_result.shape[0]

# -------------------------------------------------------------------
# 5. Load: загрузка в ClickHouse (с удалением данных за сегодня)
# -------------------------------------------------------------------
def load_to_clickhouse(**context):
    result_json = context['task_instance'].xcom_pull(key='result_data', task_ids='transform_and_join')
    if not result_json:
        return

    df = pd.read_json(result_json)
    ch_hook = ClickHouseHook(clickhouse_conn_id='clickhouse_db')
    report_date = datetime.now().date()

    # 1. Удаляем старые записи за текущую дату (чтобы избежать дублей)
    delete_sql = f"ALTER TABLE user_analytics DELETE WHERE report_date = '{report_date}'"
    ch_hook.execute(delete_sql)

    # 2. Вставляем новые записи
    # Преобразуем DataFrame в список кортежей для вставки (безопаснее, чем формировать SQL вручную)
    records = df.to_dict('records')
    insert_sql = """
        INSERT INTO user_analytics
        (user_id, username, full_name, email, prosthetic_id,
         total_sessions, total_duration, avg_response_ms, last_active, report_date)
        VALUES
    """
    values = []
    for rec in records:
        # Простое экранирование (для учебных целей; в production используйте параметризованные запросы)
        def esc(s):
            return str(s).replace("'", "\\'") if s is not None else ''
        user_id = esc(rec.get('user_id'))
        username = esc(rec.get('username'))
        full_name = esc(rec.get('full_name'))
        email = esc(rec.get('email'))
        prosthetic_id = esc(rec.get('prosthetic_id'))
        total_sessions = rec.get('total_sessions', 0)
        total_duration = rec.get('total_duration', 0)
        avg_response_ms = rec.get('avg_response_ms', 0.0)
        last_active = rec.get('last_active')
        report_date_val = rec.get('report_date')
        values.append(f"('{user_id}', '{username}', '{full_name}', '{email}', '{prosthetic_id}', {total_sessions}, {total_duration}, {avg_response_ms}, '{last_active}', '{report_date_val}')")

    if values:
        full_sql = insert_sql + ','.join(values)
        ch_hook.execute(full_sql)

# -------------------------------------------------------------------
# 6. Определение задач и зависимостей
# -------------------------------------------------------------------
start = EmptyOperator(task_id='start', dag=dag)
end = EmptyOperator(task_id='end', dag=dag)

extract_crm_task = PythonOperator(
    task_id='extract_crm',
    python_callable=extract_crm,
    dag=dag,
)

extract_telemetry_task = PythonOperator(
    task_id='extract_telemetry_agg',
    python_callable=extract_telemetry_agg,
    dag=dag,
)

transform_task = PythonOperator(
    task_id='transform_and_join',
    python_callable=transform_and_join,
    dag=dag,
)

load_task = PythonOperator(
    task_id='load_to_clickhouse',
    python_callable=load_to_clickhouse,
    dag=dag,
)

# Порядок выполнения
create_table >> start
start >> [extract_crm_task, extract_telemetry_task] >> transform_task >> load_task >> end