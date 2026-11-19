import { Icon } from "./icons";
import { PageShell } from "./SiteChrome";
import schoolImg from "./assets/school-management.jpg";
import learnImg from "./assets/personalized-learning.jpg";

function Btn({ v, size = "xl", className = "", onClick, children }) {
  return (
    <button type="button" className={`mw-btn mw-btn--${v} mw-btn--${size} ${className}`} onClick={onClick}>
      {children}
    </button>
  );
}

/* ───────────── Home ───────────── */

const SUBJECTS = [
  ["bookcheck", "CBC"],
  ["code", "Computer Science"],
  ["heart", "Life Skills"],
  ["languages", "Languages"],
  ["wallet", "Financial Literacy"],
  ["palette", "Creative Arts"],
];

function ServiceCard({ variant, image, icon, tag, title, description, features, cta, onGo }) {
  return (
    <article className={`mw-svc mw-svc--${variant}`}>
      <div className="mw-svc-img">
        <img src={image} alt={title} width="1280" height="960" />
        <div className="mw-svc-tint" />
        <span className="mw-eyebrow mw-svc-tag">{tag}</span>
      </div>
      <div className="mw-svc-body">
        <div className="mw-svc-icon-wrap"><span className="mw-svc-icon"><Icon name={icon} s={24} /></span></div>
        <h3 className="mw-svc-title">{title}</h3>
        <p className="mw-svc-desc">{description}</p>
        <ul className="mw-svc-feats">
          {features.map(([ic, text]) => (
            <li key={text}><span className="mw-feat-ico"><Icon name={ic} s={16} /></span>{text}</li>
          ))}
        </ul>
        <div className="mw-svc-cta">
          <Btn v={variant} className="mw-block-sm" onClick={onGo}>{cta} <Icon name="arrow" s={18} /></Btn>
        </div>
      </div>
    </article>
  );
}

export function SiteHome({ go }) {
  return (
    <PageShell go={go} active="site-home">
      <section className="mw-hero">
        <div className="mw-container mw-hero-in">
          <p className="mw-eyebrow mw-pillbox mw-fade"><Icon name="sparkles" s={14} /> One platform · Two ways to grow</p>
          <h1 className="mw-h1 mw-fade" style={{ animationDelay: "80ms" }}>
            Run your school.<br /><em>Grow</em> every learner.
          </h1>
          <p className="mw-lead mw-fade" style={{ animationDelay: "160ms" }}>
            MARIAN brings <strong>School Management</strong> and <strong>Personalized Learning</strong> together — built for the CBC curriculum and the skills beyond it.
          </p>
          <div className="mw-hero-cta mw-fade" style={{ animationDelay: "240ms" }}>
            <Btn v="school" onClick={() => go("site-school")}><Icon name="building" /> Explore School Management</Btn>
            <Btn v="learn" onClick={() => go("site-learning")}><Icon name="brain" /> Start Personalized Learning</Btn>
          </div>
        </div>
      </section>

      <section className="mw-container mw-services">
        <div className="mw-services-head">
          <div>
            <p className="mw-eyebrow mw-muted">Our services</p>
            <h2 className="mw-h2">Choose where you begin</h2>
          </div>
          <p className="mw-services-note">Each service has its own space, sign-in and setup — designed for the people who use it every day.</p>
        </div>
        <div className="mw-svc-grid">
          <ServiceCard
            variant="school" image={schoolImg} icon="building" tag="For schools" title="School Management"
            description="Everything your school runs on — admissions, attendance, fees, CBC assessments and parent updates — in one calm, organised place."
            features={[["users", "Learner records & admissions"], ["calendar", "Attendance & timetables"], ["receipt", "Fees, receipts & balances"], ["bookcheck", "CBC assessments & report cards"]]}
            cta="Explore School Management" onGo={() => go("site-school")}
          />
          <ServiceCard
            variant="learn" image={learnImg} icon="brain" tag="For learners & parents" title="Personalized Learning"
            description="A learning path shaped around each learner — CBC subjects plus Computer Science, Life Skills and more, at their own pace."
            features={[["sparkles", "Paths that adapt to progress"], ["bookcheck", "CBC Grades 1–12 aligned"], ["code", "Coding & digital skills"], ["heart", "Life skills & wellbeing"]]}
            cta="Start Personalized Learning" onGo={() => go("site-learning")}
          />
        </div>
      </section>

      <section className="mw-beyond">
        <div className="mw-container mw-beyond-in">
          <p className="mw-beyond-title">CBC and beyond the classroom</p>
          <ul className="mw-chips">
            {SUBJECTS.map(([ic, label]) => (
              <li key={label}><Icon name={ic} s={16} /> {label}</li>
            ))}
          </ul>
        </div>
      </section>
    </PageShell>
  );
}

/* ───────────── School Management ───────────── */

const MODULES = [
  ["users", "Admissions & records", "Enrol learners, track UPI numbers and keep every record in one profile."],
  ["calendar", "Attendance & timetables", "Mark registers in seconds and build clash-free timetables."],
  ["receipt", "Fees & finance", "Invoices, M-Pesa receipts and balances parents can see."],
  ["bookcheck", "CBC assessments", "Record competencies and generate report cards automatically."],
  ["message", "Parent communication", "Send SMS and in-app updates to one class or the whole school."],
  ["shield", "Secure by design", "Role-based access for administrators, teachers and parents."],
];

const ROLES = [
  ["usercog", "Administrators", "See the whole school at a glance."],
  ["cap", "Teachers", "Registers, marks and lesson plans."],
  ["baby", "Parents", "Progress, fees and notices."],
];

export function SiteSchool({ go }) {
  return (
    <PageShell go={go} active="site-school">
      <section className="mw-hero2 mw-hero2--school">
        <div className="mw-container mw-hero2-in">
          <div className="mw-fade">
            <p className="mw-eyebrow mw-op80">MARIAN · School Management</p>
            <h1 className="mw-h1b">Your whole school, beautifully organised.</h1>
            <p className="mw-lead2 mw-op85">From the first admission to the final report card — MARIAN keeps administrators, teachers and parents on the same page.</p>
            <div className="mw-hero2-cta">
              <Btn v="white" onClick={() => go("school-register")}>Register your school <Icon name="arrow" s={18} /></Btn>
              <Btn v="ghostschool" onClick={() => go("login")}>Sign in to your school</Btn>
            </div>
          </div>
          <div className="mw-hero2-pic">
            <img src={schoolImg} alt="A school principal reviewing the MARIAN dashboard on a tablet" width="1280" height="960" />
            <div className="mw-float">
              <p className="mw-float-k">Attendance today</p>
              <p className="mw-float-v">96.4%</p>
            </div>
          </div>
        </div>
      </section>

      <section className="mw-container mw-block">
        <div className="mw-block-head">
          <p className="mw-eyebrow mw-c-school">What's inside</p>
          <h2 className="mw-h2">Every part of running a school</h2>
        </div>
        <div className="mw-cards">
          {MODULES.map(([ic, title, text]) => (
            <div key={title} className="mw-card">
              <span className="mw-card-ico mw-card-ico--school"><Icon name={ic} s={20} /></span>
              <h3 className="mw-card-h">{title}</h3>
              <p className="mw-card-p">{text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mw-roles">
        <div className="mw-container mw-roles-in">
          <h2 className="mw-roles-h">One sign-in for every role</h2>
          <div className="mw-roles-grid">
            {ROLES.map(([ic, title, text]) => (
              <button key={title} type="button" className="mw-role" onClick={() => go("login")}>
                <span className="mw-role-ico"><Icon name={ic} s={20} /></span>
                <span className="mw-role-txt">
                  <span className="mw-role-t">{title}</span>
                  <span className="mw-role-s">{text}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      </section>
    </PageShell>
  );
}

/* ───────────── Personalized Learning ───────────── */

const TRACKS = [
  ["bookcheck", "CBC Curriculum", "Grades 1–12, aligned to KICD strands and competencies.", "Core"],
  ["code", "Computer Science", "Logic, coding, web and AI basics — from first steps to projects.", "Beyond"],
  ["heart", "Life Skills", "Communication, wellbeing, leadership and decision-making.", "Beyond"],
  ["languages", "Languages", "English, Kiswahili and French with speaking practice.", "Beyond"],
  ["wallet", "Financial Literacy", "Saving, budgeting and starting small businesses.", "Beyond"],
  ["palette", "Creative Arts", "Music, drawing and storytelling to build confidence.", "Beyond"],
];

const STEPS = [
  ["01", "Tell us about the learner", "Grade, interests and how much time they have each week."],
  ["02", "Get a personal path", "MARIAN builds a plan that mixes CBC and skills beyond it."],
  ["03", "Learn and level up", "Lessons adapt as they progress. Parents see every win."],
];

export function SiteLearning({ go }) {
  return (
    <PageShell go={go} active="site-learning">
      <section className="mw-hero2 mw-hero2--learn">
        <div className="mw-container mw-hero2-in">
          <div className="mw-fade">
            <p className="mw-eyebrow mw-c-learn">MARIAN · Personalized Learning</p>
            <h1 className="mw-h1b mw-ink">A learning path as unique as <em>every learner</em>.</h1>
            <p className="mw-lead2 mw-muted">CBC subjects plus Computer Science, Life Skills and more — paced for each learner, with progress parents can follow.</p>
            <div className="mw-hero2-cta">
              <Btn v="learn" onClick={() => go("join")}>Start Personalized Learning <Icon name="arrow" s={18} /></Btn>
              <Btn v="quiet" onClick={() => go("login")}>I already have an account</Btn>
            </div>
          </div>
          <div className="mw-hero2-pic">
            <img src={learnImg} alt="A learner coding on a laptop" width="1280" height="960" />
            <div className="mw-float">
              <p className="mw-float-k">This week</p>
              <p className="mw-float-v mw-ink">5-day streak 🔥</p>
            </div>
          </div>
        </div>
      </section>

      <section className="mw-container mw-block">
        <div className="mw-block-head">
          <p className="mw-eyebrow mw-c-learn">Learning tracks</p>
          <h2 className="mw-h2">CBC and beyond</h2>
        </div>
        <div className="mw-cards">
          {TRACKS.map(([ic, title, text, tag]) => (
            <div key={title} className="mw-card">
              <div className="mw-card-top">
                <span className="mw-card-ico mw-card-ico--learn"><Icon name={ic} s={20} /></span>
                <span className="mw-eyebrow mw-tag">{tag}</span>
              </div>
              <h3 className="mw-card-h">{title}</h3>
              <p className="mw-card-p">{text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mw-how">
        <div className="mw-container mw-how-in">
          <h2 className="mw-how-h">How it works</h2>
          <div className="mw-steps">
            {STEPS.map(([n, title, text]) => (
              <div key={n} className="mw-step">
                <p className="mw-step-n">{n}</p>
                <h3 className="mw-step-h">{title}</h3>
                <p className="mw-step-p">{text}</p>
              </div>
            ))}
          </div>
          <Btn v="white" className="mw-how-btn" onClick={() => go("join")}>Build my learning path <Icon name="arrow" s={18} /></Btn>
        </div>
      </section>
    </PageShell>
  );
}
