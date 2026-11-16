import { useEffect, useState } from "react";
import { api } from "./api";
import { Alert, Button, Card, Loading } from "./ui";
import { agePolicyLines } from "./independentLearningPolicy";
import "./independent-learning.css";

const BASE = "/api/learning/v1/";
const fallback = {
  minimum_independent_age: 10,
  adult_age: 18,
  provider_ready: false,
  capabilities: {},
  status: "provider_not_configured",
  individual_billing_separate_from_school: true,
  school_subscription_covers_learning: false,
};

export default function IndependentLearningStatus({ onBack, onSignIn }) {
  const [policy, setPolicy] = useState(null);
  const [plans, setPlans] = useState([]);
  const [error, setError] = useState("");
  const [claimToken, setClaimToken] = useState("");
  const [claimUsername, setClaimUsername] = useState("");
  const [claimPassword, setClaimPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [claimBusy, setClaimBusy] = useState(false);
  const [claimError, setClaimError] = useState("");
  const [claimNotice, setClaimNotice] = useState("");

  useEffect(() => {
    let alive = true;
    Promise.all([
      api(`${BASE}accounts/capabilities/`),
      api(`${BASE}subscriptions/plans/`),
    ])
      .then(async ([policyResponse, plansResponse]) => {
        if (!policyResponse.ok) throw new Error("Account availability could not be checked.");
        const value = await policyResponse.json();
        const planPayload = plansResponse.ok ? await plansResponse.json() : { results: [] };
        if (alive) {
          setPolicy(value);
          setPlans(Array.isArray(planPayload.results) ? planPayload.results : []);
        }
      })
      .catch(() => {
        if (alive) {
          setPolicy(fallback);
          setError("Live account availability could not be loaded. Registration remains unavailable unless the server confirms a verified provider flow.");
        }
      });
    return () => { alive = false; };
  }, []);

  const claimInvitation = async (event) => {
    event.preventDefault();
    setClaimError("");
    setClaimNotice("");
    if (claimPassword !== confirmPassword) {
      setClaimError("The passwords do not match.");
      return;
    }
    setClaimBusy(true);
    try {
      const response = await api(`${BASE}invitations/claim/`, "POST", {
        token: claimToken.trim(), username: claimUsername.trim(), password: claimPassword,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "The invitation could not be claimed.");
      setClaimNotice(`School learning account created for ${payload.username}. Sign in using Marian's existing login.`);
      setClaimToken("");
      setClaimUsername("");
      setClaimPassword("");
      setConfirmPassword("");
    } catch (cause) {
      setClaimError(cause.message || "The invitation could not be claimed.");
    } finally { setClaimBusy(false); }
  };

  return (
    <main className="a11-shell">
      <div className="a11-topline">
        <span className="a11-brand">Marian · Personalized Learning</span>
        <div className="a11-actions">
          <Button kind="secondary" onClick={onBack}>Back</Button>
          <Button kind="teal" onClick={onSignIn}>Sign in</Button>
        </div>
      </div>
      <section className="a11-content" aria-labelledby="a11-title">
        <p className="a11-kicker">Independent learning accounts</p>
        <h1 id="a11-title">Safe access starts with verified age and consent.</h1>
        <p className="a11-lead">Independent learners will use Marian authentication and a separate learning profile. Signup remains off until real age, contact, and guardian-verification providers are integrated; no verification is simulated.</p>
        {error && <Alert kind="warn">{error}</Alert>}
        {!policy ? <Loading /> : (
          <>
            <Alert kind="warn">
              <strong>Independent registration unavailable.</strong> Real contact, age, guardian-identity, and consent workflows are not integrated. This page does not collect independent-registration details.
            </Alert>
            <Card title="Approved age and guardian policy">
              <ul className="a11-policy-list">
                {agePolicyLines(policy.minimum_independent_age).map((line) => (
                  <li key={line.range}><b>{line.range}:</b> {line.rule}</li>
                ))}
              </ul>
            </Card>
            <Card title="Personalized Learning plans">
              <p className="a11-caption">This is an individual add-on. School fees and school subscriptions do not pay for it. A future school link for teacher recommendations is not available yet.</p>
              {!plans.length ? <p>Plan details are unavailable. No signup or checkout is enabled.</p> : (
                <div className="a11-list">
                  {plans.map((plan) => (
                    <article className="a11-row" key={plan.code}>
                      <div>
                        <b>{plan.name} · {plan.tier === "free" ? "Free" : "Premium"}</b>
                        <small>{plan.description || (plan.tier === "free" ? "Free access is the default." : "Premium access is not currently configured.")}</small>
                        <small>{plan.tier === "free" ? "No school billing is used." : plan.price_configured ? `Price: ${plan.amount} ${plan.currency} · ${plan.billing_interval}` : "Price and billing interval have not been approved or configured."}</small>
                      </div>
                      {plan.tier === "premium" && <Button kind="secondary" disabled>Upgrade unavailable</Button>}
                    </article>
                  ))}
                </div>
              )}
              <p className="a11-caption">Premium checkout and activation are disabled until an actual payment adapter and verified provider event flow are integrated. AI tutoring is not offered as an entitlement in this build.</p>
            </Card>
            <Card title="Claim a school invitation">
              <p className="a11-caption">Use the one-time code issued by your school. For a learner under 18, the linked Marian guardian must approve the invitation first. Unknown-age accounts remain blocked from protected learning features until age is verified.</p>
              {claimError && <Alert kind="err">{claimError}</Alert>}
              {claimNotice && <Alert>{claimNotice}</Alert>}
              <form className="a11-claim-form" onSubmit={claimInvitation} autoComplete="off">
                <label className="a11-field" htmlFor="a11-claim-token">One-time school invitation code
                  <input id="a11-claim-token" value={claimToken} onChange={(event) => setClaimToken(event.target.value)} required maxLength={256} autoComplete="off" />
                </label>
                <label className="a11-field" htmlFor="a11-claim-username">Choose a Marian username
                  <input id="a11-claim-username" value={claimUsername} onChange={(event) => setClaimUsername(event.target.value)} required maxLength={150} autoComplete="username" />
                </label>
                <label className="a11-field" htmlFor="a11-claim-password">Create a password
                  <input id="a11-claim-password" type="password" value={claimPassword} onChange={(event) => setClaimPassword(event.target.value)} required autoComplete="new-password" />
                </label>
                <label className="a11-field" htmlFor="a11-confirm-password">Confirm the password
                  <input id="a11-confirm-password" type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required autoComplete="new-password" />
                </label>
                <button className="a11-submit" type="submit" disabled={claimBusy || !claimToken.trim() || !claimUsername.trim() || !claimPassword || !confirmPassword}>
                  {claimBusy ? "Claiming invitation…" : "Claim school account"}
                </button>
              </form>
              <p className="a11-caption">The code is checked by Marian and is never saved in this browser by this form. After claiming, sign in through the existing Marian login. Existing password recovery remains unchanged.</p>
            </Card>
            <Card title="Account paths">
              <ul className="a11-policy-list">
                <li><b>School-managed learner:</b> use the school invitation and your existing Marian sign-in. Guardian approval is required where the policy applies.</li>
                <li><b>Independent learner:</b> the learner will use Marian authentication, a separate learning profile, and individual billing. Registration and guardian-assisted recovery remain unavailable until their verification workflows are integrated.</li>
                <li><b>Marian school, staff, guardian, and platform accounts:</b> continue using Marian’s existing authentication and assigned role permissions.</li>
              </ul>
              <p className="a11-caption">Account verification status: <code>{policy.status}</code> · Individual payment status: <code>{policy.premium_payment?.status || "unavailable"}</code>. Viewing this page creates no account or payment record.</p>
            </Card>
          </>
        )}
      </section>
    </main>
  );
}
