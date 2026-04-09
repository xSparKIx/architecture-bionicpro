
export const LoginPage: React.FC = () => {
    /**
     * Метод перенаправления на авторизацию
     */
    const handleLogin = () => {
        if (!process.env.REACT_APP_API_URL) {
            throw new Error('Не задан адресс Keycloak');
        }

        window.location.href = `${process.env.REACT_APP_API_URL}/login`;
    }

    return (
        <button onClick={handleLogin}>Авторизация</button>
    );
};