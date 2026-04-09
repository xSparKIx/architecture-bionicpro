import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

const BFF_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const ReportPage: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [reportData, setReportData] = useState<any>(null);

  const checkAuth = async () => {
    try {
      const response = await fetch(`${BFF_BASE_URL}/session`, {
        credentials: 'include',
      });
      if (response.ok) {
        setAuthenticated(true);
      } else {
        setAuthenticated(false);
        navigate('/login');
      }
    } catch {
      setAuthenticated(false);
      navigate('/login');
    }
  };

  useEffect(() => {
    checkAuth();
  }, [navigate]);

  const downloadReport = async () => {
    setLoading(true);
    setError(null);
    setReportData(null);

    try {
      const response = await fetch(`${BFF_BASE_URL}/api/reports`, {
        credentials: 'include',
      });

      if (response.status === 401) {
        setAuthenticated(false);
        navigate('/login');
        return;
      }

      if (!response.ok) {
        throw new Error(`Failed to fetch report: ${response.statusText}`);
      }

      const data = await response.json();
      setReportData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  if (authenticated === null) {
    return <div>Loading...</div>;
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100">
      <div className="p-8 bg-white rounded-lg shadow-md">
        <h1 className="text-2xl font-bold mb-6">Usage Reports</h1>

        <button
          onClick={downloadReport}
          disabled={loading}
          className={`px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 ${
            loading ? 'opacity-50 cursor-not-allowed' : ''
          }`}
        >
          {loading ? 'Generating Report...' : 'Download Report'}
        </button>

        {error && (
          <div className="mt-4 p-4 bg-red-100 text-red-700 rounded">
            {error}
          </div>
        )}

        {reportData && (
          <div className="mt-6 p-4 bg-gray-100 rounded">
            <h2 className="text-xl font-semibold mb-2">Report Data</h2>
            <pre className="text-sm whitespace-pre-wrap">
              {JSON.stringify(reportData, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
};

export default ReportPage;