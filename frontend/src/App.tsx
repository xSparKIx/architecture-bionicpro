import React from 'react';
import ReportPage from './components/ReportPage';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { LoginPage } from './components/LoginPage';

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<ReportPage />} />
      </Routes>
    </BrowserRouter>
  );
};

export default App;