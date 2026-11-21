import { useState } from "react";
import { BookOpen, Globe2, Landmark, Award, GraduationCap, Compass, Cpu, Briefcase, Wrench, Palette, Languages, TrendingUp, Lightbulb, ArrowRight, Sparkles, Search, ChevronDown, Check } from "lucide-react";
import "./pathway.css";

const academic = [
  { title: "CBC", desc: "PP1 – Grade 12, Kenya's Competency-Based Curriculum", icon: BookOpen, c: 1, topics: ["Pre-Primary", "Primary", "Junior School", "Senior School"] },
  { title: "Cambridge International", desc: "Primary, Lower Secondary, IGCSE & A Level", icon: Globe2, c: 2, topics: ["Primary", "Checkpoint", "IGCSE", "AS & A Level"] },
  { title: "British Curriculum", desc: "Key Stages 1–5, GCSE and A Levels", icon: Landmark, c: 3, topics: ["KS1–KS3", "GCSE", "A Levels"] },
  { title: "Pearson Edexcel", desc: "International GCSE and International A Level", icon: Award, c: 4, topics: ["iPrimary", "iLowerSecondary", "IGCSE", "IAL"] },
  { title: "University & College", desc: "Degree, diploma and certificate support", icon: GraduationCap, c: 5, topics: ["Sciences", "Engineering", "Humanities", "Exam prep"] },
  { title: "Other International", desc: "IB, American and more global curricula", icon: Compass, c: 6, topics: ["IB", "American", "Australian", "French"] },
];

const beyond = [
  { title: "Technology, Coding & AI", desc: "Build, code and create with tomorrow's tools", icon: Cpu, c: 2, topics: ["Python", "Web dev", "AI basics", "Robotics"] },
  { title: "Business & Entrepreneurship", desc: "Turn ideas into ventures that grow", icon: Briefcase, c: 4, topics: ["Startups", "Finance", "Marketing", "Leadership"] },
  { title: "Technical & Vocational", desc: "Hands-on skills for real-world work", icon: Wrench, c: 3, topics: ["Electrical", "Hospitality", "Fashion", "Agribusiness"] },
  { title: "Creative Arts & Design", desc: "Express, design and tell stories", icon: Palette, c: 5, topics: ["Graphic design", "Music", "Film", "Photography"] },
  { title: "Languages & Communication", desc: "Speak, write and connect with the world", icon: Languages, c: 6, topics: ["English", "Kiswahili", "French", "Public speaking"] },
  { title: "Professional & Career", desc: "Grow your career with confidence", icon: TrendingUp, c: 1, topics: ["CV & interviews", "Project mgmt", "Soft skills"] },
  { title: "General Knowledge & Lifelong", desc: "Stay curious at every stage of life", icon: Lightbulb, c: 7, topics: ["Health", "Financial literacy", "History", "Science"] },
];

function Stars() {
  const s = Array.from({ length: 40 }, (_, i) => ({ l: (i * 37) % 100, t: (i * 53) % 100, d: (i % 7) * 0.4 }));
  return (
    <div aria-hidden className="pl-stars">
      {s.map((x, i) => <span key={i} className="pl-star" style={{ left: `${x.l}%`, top: `${x.t}%`, animationDelay: `${x.d}s` }} />)}
    </div>
  );
}

function Orbit() {
  return (
    <div aria-hidden className="pl-orbit">
      <div className="pl-ring"><span className="pl-dot pl-d1" /><span className="pl-dot pl-d2" /></div>
      <div className="pl-ring pl-ring2"><span className="pl-dot pl-d3" /></div>
      <div className="pl-core"><Sparkles size={48} /></div>
    </div>
  );
}

function PathCard({ p, i, selected, onSelect }) {
  const [open, setOpen] = useState(false);
  const Icon = p.icon;
  return (
    <article onClick={onSelect} role="button" tabIndex={0} aria-pressed={selected}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onSelect())}
      className={"pl-glass pl-card" + (selected ? " on" : "")} style={{ animationDelay: `${i * 70}ms` }}>
      <span className="pl-check">{selected && <Check size={16} />}</span>
      <div className={"pl-ico pl-c" + p.c}><Icon size={28} /></div>
      <h3>{p.title}</h3>
      <p className="pl-lv">{p.topics.length} levels to explore</p>
      <p className="pl-desc">{p.desc}</p>
      <div className={"pl-more" + (open ? " open" : "")}><div>{p.topics.map((t) => <span key={t}>{t}</span>)}</div></div>
      <div className="pl-row">
        <button className={"pl-see" + (open ? " open" : "")} onClick={(e) => { e.stopPropagation(); setOpen(!open); }}>{open ? "Hide" : "See"} levels <ChevronDown size={16} /></button>
        <button className="pl-choose" aria-label={`Choose ${p.title}`} onClick={(e) => { e.stopPropagation(); onSelect(); }}>{selected ? "Chosen" : "Choose"} <ArrowRight size={16} /></button>
      </div>
    </article>
  );
}

function Section({ id, eyebrow, title, sub, items, q, sel, setSel }) {
  const list = items.filter((p) => (p.title + p.desc + p.topics.join(" ")).toLowerCase().includes(q.toLowerCase()));
  if (!list.length) return null;
  return (
    <section id={id} className="pl-wrap pl-sec">
      <p className="pl-eyebrow">{eyebrow}</p>
      <h2 className="pl-h2">{title}</h2>
      <p className="pl-sec-sub">{sub}</p>
      <div className="pl-grid">
        {list.map((p, i) => <PathCard key={p.title} p={p} i={i} selected={sel === p.title} onSelect={() => setSel(sel === p.title ? null : p.title)} />)}
      </div>
    </section>
  );
}

export default function PathwayPicker({ onContinue }) {
  const [q, setQ] = useState("");
  const [tab, setTab] = useState("all");
  const [sel, setSel] = useState(null);
  const tabs = [
    { k: "all", l: "All pathways", n: academic.length + beyond.length },
    { k: "academic", l: "Academic", n: academic.length },
    { k: "beyond", l: "Beyond", n: beyond.length },
  ];
  const match = (p) => (p.title + p.desc + p.topics.join(" ")).toLowerCase().includes(q.toLowerCase());
  const empty = q && ![...academic, ...beyond].some(match);
  return (
    <main className="pl pl-main">
      <Stars />
      <header className="pl-glass pl-head"><div className="pl-wrap">
        <span className="pl-logo"><b>Marian</b> <i>Learning</i></span>
        <span className="pl-step">Step 1 of 3 · Choose a pathway</span>
      </div></header>
      <section className="pl-wrap pl-hero">
        <div>
          <span className="pl-glass pl-chip"><Sparkles size={14} /> Your personalized learning universe</span>
          <h1 className="pl-h1">Where will your <span className="pl-gold">curiosity</span> take you?</h1>
          <p className="pl-sub">Pick a pathway built around you — from classroom curricula to the skills that shape your future.</p>
          <label className="pl-glass pl-search"><Search size={20} />
            <input aria-label="Search pathways" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search IGCSE, coding, Kiswahili…" />
          </label>
        </div>
        <Orbit />
      </section>
      <div className="pl-wrap pl-tabbar"><div role="tablist" className="pl-glass pl-tabs">
        {tabs.map((t) => <button key={t.k} role="tab" aria-selected={tab === t.k} className="pl-tab" onClick={() => setTab(t.k)}>{t.l}<span>{t.n}</span></button>)}
      </div></div>
      {empty && <p className="pl-empty">No pathways match "{q}". <button onClick={() => setQ("")}>Clear search</button></p>}
      {tab !== "beyond" && <Section id="academic" q={q} sel={sel} setSel={setSel} eyebrow="Pathway 01" title="Academic Learning" sub="Master your curriculum with lessons, practice and guidance tailored to your level." items={academic} />}
      {tab !== "academic" && <Section id="beyond" q={q} sel={sel} setSel={setSel} eyebrow="Pathway 02" title="Beyond the Curriculum" sub="Discover skills, passions and careers that go far beyond the classroom." items={beyond} />}
      <div className={"pl-bar" + (sel ? " on" : "")}><div className="pl-bar-in">
        <div><p>Your pathway</p><p>{sel}</p></div>
        <button className="pl-go" onClick={() => onContinue && onContinue(sel)}>Continue <ArrowRight size={16} /></button>
      </div></div>
      <footer className="pl-foot">© Marian Personalized Learning</footer>
    </main>
  );
}
