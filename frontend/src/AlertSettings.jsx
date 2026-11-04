import { useEffect, useState } from "react";
import { api } from "./api";
import { useToast } from "./toastctx";
import { Card, Loading } from "./ui";
import "./announce.css";

// Lets every signed-in person choose whether alerts also reach them by email or SMS.
export default function AlertSettings() {
  const toast = useToast();
  const [p, setP] = useState(null), [busy, setBusy] = useState("");
  useEffect(() => { api("/api/me/alert-preferences/").then(async (r) => r.ok && setP(await r.json())); }, []);
  if (!p) return <Card title="Alert settings"><Loading /></Card>;
  const flip = async (k) => {
    setBusy(k);
    const r = await api("/api/me/alert-preferences/", "PATCH", { [k]: !p[k] });
    setBusy("");
    if (r.ok) { setP(await r.json()); toast("Alert settings saved", "ok"); } else toast("Could not save", "err");
  };
  return (<Card title="Alert settings">
    <p className="sub">You always see alerts and announcements inside Marian. Choose whether they also reach you outside the app.</p>
    <label className="an-check">
      <input type="checkbox" checked={p.email_alerts} disabled={busy === "email_alerts"} onChange={() => flip("email_alerts")} />
      Email me {p.email ? <small>({p.email})</small> : <small>(no email address on your account)</small>}
    </label>
    <label className="an-check">
      <input type="checkbox" checked={p.sms_alerts} disabled={busy === "sms_alerts"} onChange={() => flip("sms_alerts")} />
      SMS me {p.phone ? <small>({p.phone}{p.phone_valid ? "" : ", not a valid number"})</small> : <small>(no phone number on your account)</small>}
    </label>
  </Card>);
}
