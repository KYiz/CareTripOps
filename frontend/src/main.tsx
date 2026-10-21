import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { I18nProvider } from './i18n';
import './styles.css';
import './travel.css';
import './redesign.css';
import './v4.css';
import './account.css';
import './senior.css';

createRoot(document.getElementById('root')!).render(<React.StrictMode><I18nProvider><App /></I18nProvider></React.StrictMode>);
