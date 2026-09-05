import axios from 'axios';

const apiClient = axios.create({
  baseURL: process.env.REACT_APP_API_URL || 'http://127.0.0.1:5001/api',
  headers: { 'Content-Type': 'application/json' },
});

export default apiClient;
