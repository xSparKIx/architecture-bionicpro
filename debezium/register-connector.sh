curl -X POST -H "Content-Type: application/json" --data '{
  "name": "postgres-cdc-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "plugin.name": "pgoutput",
    "database.hostname": "postgres-crm",
    "database.port": "5432",
    "database.user": "postgres",
    "database.password": "postgres",
    "database.dbname": "crmdb",
    "database.server.name": "crm",
    "table.include.list": "public.customers",
    "publication.name": "debezium_pub",
    "topic.prefix": "crm",
    "key.converter": "org.apache.kafka.connect.json.JsonConverter",
    "value.converter": "org.apache.kafka.connect.json.JsonConverter",
    "key.converter.schemas.enable": "false",
    "value.converter.schemas.enable": "false"
  }
}' http://localhost:8083/connectors