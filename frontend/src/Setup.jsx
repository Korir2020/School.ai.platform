import { useEffect, useMemo, useRef, useState } from "react";
import { api, listAll as list, upload } from "./api";
import { useToast } from "./toastctx";
import { Alert, Button, Input, Select, Card, DataTable, Loading, ErrorState, Modal } from "./ui";
import SetupSection from "./SetupSection";

const paths = ["streams", "subjects", "class-levels", "curriculums"];
const LOGO_MAX = 2 * 1024 * 1024;
const LOGO_TYPES = ["image/png", "image/jpeg", "image/webp"];

function impactLines(impact) {
  return Object.entries(impact || {})
    .filter(([, value]) => typeof value === "number" && value > 0)
    .map(([key, value]) => `${key.replaceAll("_", " ")}: ${value}`);
}

export default function Setup() {
  const toast = useToast();
  const logoInput = useRef(null);
  const [x, setX] = useState(null);
  const [bad, setBad] = useState(false);
  const [catalog, setCatalog] = useState(null);
  const [catalogBusy, setCatalogBusy] = useState(false);
  const [selected, setSelected] = useState([]);
  const [busy, setBusy] = useState(false);
  const [branding, setBranding] = useState(null);
  const [logo, setLogo] = useState(null);
  const [logoError, setLogoError] = useState("");
  const [logoPreview, setLogoPreview] = useState(null);
  const [idt, setIdt] = useState({});
  const [newStream, setNewStream] = useState({ class_level: "", name: "" });
  const [newSubject, setNewSubject] = useState({ name: "", code: "" });
  const [edit, setEdit] = useState(null);
  const [deleteAsk, setDeleteAsk] = useState(null);

  const load = async () => {
    try {
      const get = (p) => list("/api/" + p + "/");
      const [sm, sj, cl, cu, br, setup, cat] = await Promise.all([
        ...paths.map(get),
        api("/api/school/branding/"),
        api("/api/setup/"),
        api("/api/setup/subject-catalog/"),
      ]);
      const curriculumById = Object.fromEntries(cu.map((row) => [row.id, row]));
      const levels = cl.map((row) => ({
        ...row,
        curriculum_code: (curriculumById[row.curriculum] || {}).code || "",
        label: `${(curriculumById[row.curriculum] || {}).code || ""} ${row.name || ""}`.trim(),
      }));
      const levelById = Object.fromEntries(levels.map((row) => [row.id, row]));
      setX({
        sj,
        cl: levels,
        sm: sm.map((row) => ({ ...row, label: `${(levelById[row.class_level] || {}).label || ""} ${row.name}`.trim() })),
        checklist: setup.ok ? (await setup.json()).checklist : {},
      });
      if (br.ok) setBranding(await br.json());
      if (cat.ok) setCatalog(await cat.json());
      else setCatalog(null);
      setBad(false);
    } catch {
      setBad(true);
    }
  };

  useEffect(() => {
    return () => {
      if (logoPreview) URL.revokeObjectURL(logoPreview);
    };
  }, [logoPreview]);

  useEffect(() => {
    // This effect initiates an async API read; its state updates occur after the requests resolve.
    // oxlint-disable-next-line react/set-state-in-effect
    load();
  }, []);

  const post = async (path, body, ok) => {
    setBusy(true);
    const r = await api(path, "POST", body);
    const j = await r.json().catch(() => ({}));
    setBusy(false);
    if (r.ok) {
      toast(ok, "ok");
      await load();
      return true;
    }
    toast(j.detail || JSON.stringify(j), "err");
    return false;
  };

  const saveIdentity = async () => {
    setBusy(true);
    const fd = new FormData();
    Object.entries(idt).forEach(([key, value]) => fd.append(key, value));
    const r = await upload("/api/school/branding/", fd);
    setBusy(false);
    if (r.ok) {
      setIdt({});
      toast("Saved", "ok");
      load();
    } else {
      const j = await r.json().catch(() => ({}));
      toast(j.detail || "Not saved", "err");
    }
  };

  const chooseLogo = (file) => {
    setLogoError("");
    if (!file) return;
    if (!LOGO_TYPES.includes(file.type)) {
      setLogoError("Choose a PNG, JPG, JPEG, or WEBP image.");
      return;
    }
    if (file.size > LOGO_MAX) {
      setLogoError("Logo must be no larger than 2 MB.");
      return;
    }
    setLogoPreview(URL.createObjectURL(file));
    setLogo(file);
  };

  const uploadLogo = async () => {
    if (!logo) return;
    setBusy(true);
    const fd = new FormData();
    fd.append("logo", logo);
    const r = await upload("/api/school/branding/", fd);
    setBusy(false);
    if (r.ok) {
      toast("Logo uploaded", "ok");
      setLogo(null);
      setLogoPreview(null);
      await load();
    } else {
      const j = await r.json().catch(() => ({}));
      setLogoError(j.detail || "Logo upload failed.");
    }
  };

  const removeLogo = async () => {
    setBusy(true);
    const r = await api("/api/school/branding/", "DELETE");
    setBusy(false);
    if (r.ok) {
      toast("Logo removed", "ok");
      setLogo(null);
      setLogoPreview(null);
      load();
    } else {
      const j = await r.json().catch(() => ({}));
      toast(j.detail || "Logo could not be removed.", "err");
    }
  };

  const openEdit = (kind, row) => setEdit({
    kind,
    row,
    name: row.name,
    code: row.code || "",
    is_active: row.is_active,
  });

  const saveEdit = async () => {
    if (!edit || !edit.name.trim()) return;
    const body = { name: edit.name.trim(), is_active: !!edit.is_active };
    if (edit.kind === "subject") body.code = edit.code.trim();
    const ok = await post(`/api/${edit.kind}s/${edit.row.id}/`, body, `${edit.kind === "subject" ? "Subject" : "Stream"} updated`);
    if (ok) setEdit(null);
  };

  const requestDelete = async (kind, row) => {
    setBusy(true);
    const r = await api(`/api/${kind}s/${row.id}/`, "DELETE", { confirm: false });
    const j = await r.json().catch(() => ({}));
    setBusy(false);
    if (r.status === 409 && j.impact) {
      setDeleteAsk({ kind, row, detail: j.detail, impact: j.impact, blocked: !!j.blocked });
    } else if (!r.ok) {
      toast(j.detail || "Could not prepare deletion.", "err");
    }
  };

  const confirmDelete = async () => {
    if (!deleteAsk || deleteAsk.blocked) return;
    setBusy(true);
    const r = await api(`/api/${deleteAsk.kind}s/${deleteAsk.row.id}/`, "DELETE", { confirm: true });
    const j = await r.json().catch(() => ({}));
    setBusy(false);
    if (r.ok) {
      toast(`${deleteAsk.kind === "subject" ? "Subject" : "Stream"} deleted`, "ok");
      setDeleteAsk(null);
      load();
    } else {
      toast(j.detail || "Could not delete.", "err");
    }
  };

  const toggleCatalog = (item) => {
    const key = `${item.definition_id}-${item.class_level_id}`;
    setSelected((current) => current.includes(key)
      ? current.filter((value) => value !== key)
      : [...current, key]);
  };

  const addCatalogSubjects = async () => {
    const selections = catalog.groups.flatMap((group) => group.subjects)
      .filter((item) => selected.includes(`${item.definition_id}-${item.class_level_id}`))
      .map((item) => ({ definition_id: item.definition_id, class_level_id: item.class_level_id }));
    setCatalogBusy(true);
    const r = await api("/api/setup/subjects/bulk/", "POST", { selections });
    const j = await r.json().catch(() => ({}));
    setCatalogBusy(false);
    if (!r.ok) {
      toast(j.detail || "Subjects could not be added.", "err");
      return;
    }
    toast(`${j.created_count} subject${j.created_count === 1 ? "" : "s"} added${j.skipped_count ? ` · ${j.skipped_count} already present` : ""}`, "ok");
    setSelected([]);
    load();
  };

  const scols = [
    { label: "Class / stream", key: "label", sort: true },
    { label: "Actions", render: (row) => <div className="s2-row-actions"><Button kind="ghost" size="sm" onClick={() => openEdit("stream", row)}>Edit</Button><Button kind="ghost" size="sm" onClick={() => requestDelete("stream", row)}>Delete</Button></div> },
  ];
  const jcols = [
    { label: "Subject", key: "name", sort: true },
    { label: "Code", key: "code", sort: true },
    { label: "Curriculum learning area", key: "definition_name", render: (row) => row.definition_name || "School-created" },
    { label: "Actions", render: (row) => <div className="s2-row-actions"><Button kind="ghost" size="sm" onClick={() => openEdit("subject", row)}>Edit</Button><Button kind="ghost" size="sm" onClick={() => requestDelete("subject", row)}>Delete</Button></div> },
  ];
  const selectedCount = selected.length;
  const identityComplete = !!(x && x.checklist && x.checklist.profile);
  const activeStreams = x ? x.sm.filter((row) => row.is_active).length : 0;
  const activeSubjects = x ? x.sj.filter((row) => row.is_active).length : 0;
  const classesComplete = activeStreams > 0 && activeSubjects > 0;
  const catalogGroups = useMemo(() => (catalog && catalog.groups) || [], [catalog]);

  if (bad) return <ErrorState text="Could not load setup." onRetry={load} />;
  if (!x) return <Loading />;

  return (
    <div className="s2-wrap">
      <SetupSection id="setup-identity" title="School identity" summary={branding && branding.logo_url ? "Profile details and logo saved" : "Profile details saved · logo optional"} complete={identityComplete}>
        <div className="s2-panel s2-ident">
          <div>
            <Input id="su-motto" label="School motto" value={idt.motto ?? (branding && branding.motto) ?? ""} onChange={(e) => setIdt({ ...idt, motto: e.target.value })} />
            <Input id="su-principal" label="Principal's name" value={idt.principal_name ?? (branding && branding.principal_name) ?? ""} onChange={(e) => setIdt({ ...idt, principal_name: e.target.value })} />
            <p><Button kind="teal" busy={busy} disabled={busy || !Object.keys(idt).length} onClick={saveIdentity}>Save motto and principal</Button></p>
          </div>
          <div className="s2-logo-area">
            <p className="sub">Classic upload area, like Migration Centre. PNG, JPG, JPEG, or WEBP up to 2 MB. Server checks the real image type and size.</p>
            <div className="s2-logo-preview">
              {logoPreview ? <img src={logoPreview} alt="Selected logo preview" /> : branding && branding.logo_url ? <img src={branding.logo_url} alt={`${branding.name} logo`} /> : <span>No logo uploaded</span>}
              {logo && <b>{logo.name}</b>}
            </div>
            <label className="s2-logo-drop" htmlFor="su-logo">
              <strong>{logo ? "Logo selected" : "Choose or replace logo"}</strong>
              <span>PNG, JPG, JPEG, or WEBP · max 2 MB</span>
              <input id="su-logo" ref={logoInput} type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => { chooseLogo(e.target.files[0]); e.target.value = ""; }} />
            </label>
            {logoError && <Alert kind="err">{logoError}</Alert>}
            <div className="s2-logo-actions">
              <Button kind="teal" busy={busy} disabled={!logo || busy} onClick={uploadLogo}>{branding && branding.logo_url ? "Replace logo" : "Upload logo"}</Button>
              {branding && branding.logo_url && <Button kind="ghost" busy={busy} disabled={busy} onClick={removeLogo}>Remove logo</Button>}
            </div>
          </div>
        </div>
      </SetupSection>

      <SetupSection id="setup-classes" title="Classes and subjects" summary={`${activeStreams} active stream${activeStreams === 1 ? "" : "s"} · ${activeSubjects} active subject${activeSubjects === 1 ? "" : "s"}`} complete={classesComplete}>
        <div className="s2-cols even"><div className="s2-stack">
          <Card title="Streams">
            <DataTable cols={scols} rows={x.sm} search="Search streams" empty="No streams yet" />
          </Card>
          <Card title="Add stream">
            <Select id="su-lvl" label="Class level" value={newStream.class_level} onChange={(e) => setNewStream({ ...newStream, class_level: e.target.value })}>
              <option value="">Select...</option>
              {x.cl.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
            </Select>
            <Input id="su-sn" label="Stream name" value={newStream.name} onChange={(e) => setNewStream({ ...newStream, name: e.target.value })} />
            <Button kind="teal" busy={busy} disabled={!newStream.class_level || !newStream.name.trim()} onClick={async () => {
              if (await post("/api/streams/", { class_level: newStream.class_level, name: newStream.name.trim(), is_active: true }, "Stream added")) setNewStream({ class_level: "", name: "" });
            }}>Add stream</Button>
          </Card>
        </div><div className="s2-stack">
          <Card title="Subjects">
            <DataTable cols={jcols} rows={x.sj} search="Search subjects" empty="No subjects yet" />
          </Card>
          <Card title="Add from Marian catalogue">
            <p>Tick several subjects and add them at once. Options are current rows from Marian's CBC and 8-4-4 fixture-backed catalogue, grouped by level. Existing subjects are marked and are never duplicated.</p>
            <Alert kind="info">{catalog ? catalog.notice : "Catalogue is not available for this school type yet."}</Alert>
            {catalogGroups.length === 0 ? <p className="s2-mut">No catalogue levels are available for this school type. Shared class levels remain read-only.</p> : catalogGroups.map((group) => (
              <div className="s2-catalog-group" key={`${group.curriculum_code}-${group.class_level_id}`}>
                <div className="s2-catalog-head"><b>{group.class_level_name}</b><span>{group.curriculum_code} · {group.subjects.length} options</span></div>
                <div className="s2-catalog-list">
                  {group.subjects.map((item) => {
                    const key = `${item.definition_id}-${item.class_level_id}`;
                    return <label className={"s2-catalog-item" + (item.already_added ? " exists" : "")} key={key}>
                      <input type="checkbox" checked={item.already_added || selected.includes(key)} disabled={item.already_added} onChange={() => toggleCatalog(item)} />
                      <span><b>{item.name}</b><small>Marian internal code: {item.code}</small></span>
                      {item.already_added && <em>Already added</em>}
                    </label>;
                  })}
                </div>
              </div>
            ))}
            <Button kind="teal" busy={catalogBusy} disabled={!selectedCount || catalogBusy} onClick={addCatalogSubjects}>Add {selectedCount || "selected"} subject{selectedCount === 1 ? "" : "s"}</Button>
            <p className="s2-hint">Class-level catalogue rows are shared global curriculum data. Marian does not offer school-level class edit or delete here.</p>
          </Card>
          <Card title="Add school-created subject">
            <Input id="su-bn" label="Subject name" value={newSubject.name} onChange={(e) => setNewSubject({ ...newSubject, name: e.target.value })} />
            <Input id="su-bc" label="Marian internal code" value={newSubject.code} onChange={(e) => setNewSubject({ ...newSubject, code: e.target.value })} />
            <Button kind="teal" busy={busy} disabled={!newSubject.name.trim() || !newSubject.code.trim()} onClick={async () => {
              if (await post("/api/subjects/", { name: newSubject.name.trim(), code: newSubject.code.trim(), is_active: true }, "Subject added")) setNewSubject({ name: "", code: "" });
            }}>Add subject</Button>
          </Card>
        </div></div>
      </SetupSection>

      {edit && <Modal title={`Edit ${edit.kind}`} onClose={() => setEdit(null)} actions={<><Button kind="secondary" onClick={() => setEdit(null)}>Cancel</Button><Button kind="teal" busy={busy} disabled={!edit.name.trim()} onClick={saveEdit}>Save</Button></>}>
        <Input id="setup-edit-name" label="Name" value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} />
        {edit.kind === "subject" && <Input id="setup-edit-code" label="Marian internal code" value={edit.code} onChange={(e) => setEdit({ ...edit, code: e.target.value })} />}
        <label className="s2-check"><input type="checkbox" checked={!!edit.is_active} onChange={(e) => setEdit({ ...edit, is_active: e.target.checked })} /> Active</label>
      </Modal>}

      {deleteAsk && <Modal title={`Delete ${deleteAsk.kind}?`} onClose={() => setDeleteAsk(null)} actions={<><Button kind="secondary" onClick={() => setDeleteAsk(null)}>Cancel</Button>{!deleteAsk.blocked && <Button kind="danger" busy={busy} onClick={confirmDelete}>Delete after confirmation</Button>}</>}>
        <p>{deleteAsk.detail}</p>
        {impactLines(deleteAsk.impact).length > 0 && <ul className="s2-errs">{impactLines(deleteAsk.impact).map((line) => <li key={line}>{line}</li>)}</ul>}
        {deleteAsk.impact && deleteAsk.impact.enrollment_rule && <p className="s2-hint">{deleteAsk.impact.enrollment_rule}</p>}
        {deleteAsk.impact && deleteAsk.impact.marks_rule && <p className="s2-hint">{deleteAsk.impact.marks_rule}</p>}
        {deleteAsk.impact && deleteAsk.impact.registration_rule && <p className="s2-hint">{deleteAsk.impact.registration_rule}</p>}
        {deleteAsk.blocked && <Alert kind="err">This deletion is blocked. Remove the protected subject registrations first.</Alert>}
      </Modal>}
    </div>
  );
}
