import { Mark, Wordmark } from "./brand";
import { Button } from "./ui";
import "./legal.css";

// Add each paragraph as a string once the final wording is ready.
const PAGES = {
  privacy: { title: "Privacy Policy", body: [] },
  terms: { title: "Terms of Service", body: [] },
};

export default function LegalPage({ kind, onBack }) {
  const page = PAGES[kind] || PAGES.privacy;
  return (
    <div className="mk wall">
      <header className="mk-bar">
        <span className="mk-brand">
          <Mark size={26} />
          <Wordmark height={14} />
        </span>
      </header>
      <main className="lg-main">
        <h1>{page.title}</h1>
        <div className="lg-card">
          {page.body.length === 0 ? (
            <p>This page is being prepared and will be published soon.</p>
          ) : (
            page.body.map((t) => <p key={t}>{t}</p>)
          )}
        </div>
        <div className="lg-back">
          <Button kind="secondary" onClick={onBack}>Back</Button>
        </div>
      </main>
    </div>
  );
}
