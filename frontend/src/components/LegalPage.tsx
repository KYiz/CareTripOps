import { useI18n } from '../i18n';
import { PRIVACY, TERMS } from '../legal';

/** Terms of Use or Privacy Notice in the current language. */
export default function LegalPage({ kind }: { kind: 'terms' | 'privacy' }) {
  const { lang } = useI18n();
  const doc = (kind === 'terms' ? TERMS : PRIVACY)[lang];
  return <main className="ct-account-page ct-legal">
    <p className="ct-kicker">CARETRIP</p>
    <h1>{doc.title}</h1>
    <p className="ct-legal-updated">{doc.updated}</p>
    <p className="ct-legal-template" role="note">{doc.template}</p>
    {doc.sections.map(section => <section key={section.heading}>
      <h2>{section.heading}</h2>
      {section.paragraphs.map(text => <p key={text}>{text}</p>)}
    </section>)}
  </main>;
}
