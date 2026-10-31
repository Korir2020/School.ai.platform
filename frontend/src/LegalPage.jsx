import { Mark, Wordmark } from "./brand";
import { Button } from "./ui";
import "./legal.css";
import privacyText from "./legal-privacy.txt?raw";
import termsText from "./legal-terms.txt?raw";

// Wording lives in legal-privacy.txt and legal-terms.txt. A line starting with ## is a heading, ### a subheading, - a bullet; anything else is a paragraph.
const PAGES = {
  privacy: { title: "Privacy Policy", body: privacyText.split("\n").filter(Boolean) },
  terms: { title: "Terms of Service", body: termsText.split("\n").filter(Boolean) },
};

function renderBody(lines) {
  const out = [];
  let items = [];
  const flush = () => {
    if (items.length) {
      const list = items;
      out.push(<ul key={"ul-" + list[0]}>{list.map((t) => <li key={t}>{t}</li>)}</ul>);
      items = [];
    }
  };
  lines.forEach((t) => {
    if (t.startsWith("- ")) {
      items.push(t.slice(2));
      return;
    }
    flush();
    if (t.startsWith("### ")) out.push(<h3 key={t}>{t.slice(4)}</h3>);
    else if (t.startsWith("## ")) out.push(<h2 key={t}>{t.slice(3)}</h2>);
    else out.push(<p key={t}>{t}</p>);
  });
  flush();
  return out;
}

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
            renderBody(page.body)
          )}
        </div>
        <div className="lg-back">
          <Button kind="secondary" onClick={onBack}>Back</Button>
        </div>
      </main>
    </div>
  );
}
