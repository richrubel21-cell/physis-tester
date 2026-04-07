import axios from "axios";

const API_BASE = import.meta.env.VITE_API_URL || "https://physis-tester.onrender.com";

const client = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
});

export default client;
