import SetupWizard from "./SetupWizard";
import Terms from "./Terms";
import Setup from "./Setup";
import { SchoolExport } from "./Backups";
import "./setup2.css";

const NAV = [["setup-progress", "Progress"], ["setup-terms", "Calendar"], ["setup-identity", "Identity"], ["setup-classes", "Classes & subjects"], ["setup-papers", "Papers"], ["setup-export", "Export"]];

export default function SetupPage({ me, d, go }) {
  const jump = (id) => { const el = document.getElementById(id); if (el) el.scrollIntoView({ behavior: "smooth", block: "start" }); };
  const owner = me && !me.is_deputy;
  return (
    <div className="plain s2">
      <header className="s2-head">
        <div>
          <p className="s2-eye">School configuration</p>
          <h2>Setup</h2>
          <p className="s2-mut">Profile, calendar, classes and subjects — everything the rest of Marian depends on.</p>
        </div>
        <div className={"s2-term" + (d && d.active_term ? " live" : "")}><i />{d && d.active_term ? d.active_term.name + " " + (d.active_term.academic_year || "") : "No active term"}</div>
      </header>
      <nav className="s2-nav" aria-label="Setup sections">
        {NAV.filter(([id]) => id !== "setup-export" || owner).map(([id, l]) => <button type="button" key={id} onClick={() => jump(id)}>{l}</button>)}
      </nav>
      <SetupWizard go={jump} />
      <Terms />
      <Setup />
      {owner && <section className="s2-sec" id="setup-export"><SchoolExport /></section>}
    </div>
  );
}
