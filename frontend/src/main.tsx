import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles.css';
import './travel.css';
import './redesign.css';
import './v4.css';

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
