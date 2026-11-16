import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { Alert, Button, Card, EmptyState, Loading } from "./ui";
import "./independent-learning.css";

const BASE = "/api/learning/v1/";
const isLearner = (role) => role === "student" || role === "public_learner";
const guardianCandidateLabel = (student) => {
  if (!student.guardian_required) return "";
  return student.guardian_available ? " · guardian approval required" : " · no active linked guardian";
};

async function readJson(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || payload.code || "This account operation is unavailable.");
  return payload;
}

export default function LearningAccountSettings({ me }) {
  const role = me?.role || "";
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selectedStudentId, setSelectedStudentId] = useState("");
  const [issuedInvitation, setIssuedInvitation] = useState(null);

  const load = useCallback(async () => {
    setError("");
    try {
      if (role === "school_admin") {
        const [summaryResponse, accountsResponse, invitationsResponse, candidatesResponse] = await Promise.all([
          api(`${BASE}admin/learning-summary/`),
          api(`${BASE}admin/learning-accounts/`),
          api(`${BASE}admin/invitations/`),
          api(`${BASE}admin/invitation-candidates/`),
        ]);
        const [summary, accounts, invitations, candidates] = await Promise.all([
          readJson(summaryResponse), readJson(accountsResponse), readJson(invitationsResponse), readJson(candidatesResponse),
        ]);
        setData({ summary, accounts: accounts.results || [], accountsTruncated: accounts.truncated,
          invitations: invitations.results || [], invitationsTruncated: invitations.truncated,
          candidates: candidates.results || [], candidatesTruncated: candidates.truncated });
      } else if (role === "parent") {
        const [learnersResponse, invitationsResponse] = await Promise.all([
          api(`${BASE}guardians/learners/`),
          api(`${BASE}guardians/invitations/`),
        ]);
        const [guardianData, invitationData] = await Promise.all([
          readJson(learnersResponse), readJson(invitationsResponse),
        ]);
        setData({ learners: guardianData.results || [], guardianInvitations: invitationData.results || [],
          guardianInvitationsTruncated: invitationData.truncated });
      } else if (isLearner(role)) {
        const [requestsResponse, profileResponse, subscriptionResponse] = await Promise.all([
          api(`${BASE}account/lifecycle-requests/`),
          api(`${BASE}me/`),
          api(`${BASE}subscriptions/me/`),
        ]);
        const requests = await readJson(requestsResponse);
        let profile = null;
        if (profileResponse.ok) profile = await profileResponse.json();
        const subscription = subscriptionResponse.ok ? await subscriptionResponse.json() : null;
        setData({ requests: requests.results || [], profile, subscription });
      } else {
        setData({ unavailable: true });
      }
    } catch (cause) {
      setData(null);
      setError(cause.message || "This account view is unavailable.");
    }
  }, [role]);

  useEffect(() => { load(); }, [load]);

  const submitLifecycle = async (requestType) => {
    const wording = requestType === "deletion"
      ? "Requesting deletion blocks protected learning access immediately. No records will be permanently deleted until a retention policy and review process are configured. Continue?"
      : "Requesting suspension blocks protected learning access immediately. You can cancel the pending request from this page. Continue?";
    if (!window.confirm(wording)) return;
    setBusy(true);
    setNotice("");
    try {
      const response = await api(`${BASE}account/lifecycle-requests/`, "POST", { request_type: requestType });
      const payload = await readJson(response);
      setNotice(payload.detail || "Your request was recorded. No data was permanently deleted.");
      await load();
    } catch (cause) {
      setError(cause.message || "The request could not be recorded.");
    } finally { setBusy(false); }
  };

  const cancelLifecycle = async (requestId) => {
    setBusy(true);
    try {
      const response = await api(`${BASE}account/lifecycle-requests/${requestId}/cancel/`, "POST", {});
      await readJson(response);
      setNotice("The pending account request was cancelled.");
      await load();
    } catch (cause) {
      setError(cause.message || "The request could not be cancelled.");
    } finally { setBusy(false); }
  };

  const withdrawConsent = async (profileId) => {
    if (!window.confirm("Withdraw guardian consent? The linked learner will immediately lose access to protected learning features.")) return;
    setBusy(true);
    try {
      const response = await api(`${BASE}guardians/learners/${profileId}/consent/withdraw/`, "POST", {});
      const payload = await readJson(response);
      setNotice(payload.detail || "Consent withdrawn.");
      await load();
    } catch (cause) {
      setError(cause.message || "Consent could not be withdrawn.");
    } finally { setBusy(false); }
  };

  const changeSchoolAccount = async (row) => {
    const next = row.account_status === "suspended" ? "active" : "suspended";
    const prompt = next === "suspended"
      ? "Suspend this school-managed learning account? Protected learning access will stop immediately."
      : "Restore this school-managed learning account? Age and guardian-consent checks still apply.";
    if (!window.confirm(prompt)) return;
    setBusy(true);
    try {
      const response = await api(`${BASE}admin/learning-accounts/${row.profile_id}/state/`, "POST", { account_status: next });
      await readJson(response);
      setNotice(`Account state changed to ${next}.`);
      await load();
    } catch (cause) {
      setError(cause.message || "Account state could not be changed.");
    } finally { setBusy(false); }
  };

  const issueInvitation = async () => {
    if (!selectedStudentId) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await api(`${BASE}admin/invitations/`, "POST", { student_id: Number(selectedStudentId) });
      const payload = await readJson(response);
      setIssuedInvitation(payload);
      setSelectedStudentId("");
      setNotice("Invitation created. Deliver the one-time code securely to the linked guardian; Marian did not send a message.");
      await load();
    } catch (cause) {
      setError(cause.message || "The invitation could not be created.");
    } finally { setBusy(false); }
  };

  const revokeInvitation = async (invitation) => {
    if (!window.confirm(`Revoke the invitation for ${invitation.student_name}? Its one-time code will stop working.`)) return;
    setBusy(true);
    try {
      const response = await api(`${BASE}admin/invitations/${invitation.id}/revoke/`, "POST", {});
      const payload = await readJson(response);
      setNotice(payload.detail || "Invitation revoked.");
      await load();
    } catch (cause) {
      setError(cause.message || "The invitation could not be revoked.");
    } finally { setBusy(false); }
  };

  const checkInvitationDelivery = async (invitation) => {
    setBusy(true);
    try {
      const response = await api(`${BASE}admin/invitations/${invitation.id}/resend/`, "POST", {});
      const payload = await response.json().catch(() => ({}));
      setNotice(payload.detail || "Invitation delivery is unavailable. No email or SMS was sent and the one-time code was not changed.");
      await load();
    } catch (cause) {
      setError(cause.message || "Invitation delivery status could not be checked.");
    } finally { setBusy(false); }
  };

  const approveGuardianInvitation = async (invitation) => {
    if (!window.confirm(`Approve the learning invitation for ${invitation.student_name}? This records guardian consent for this school-managed account.`)) return;
    setBusy(true);
    try {
      const response = await api(`${BASE}invitations/${invitation.id}/guardian-approval/`, "POST", {});
      const payload = await readJson(response);
      setNotice(payload.detail || "Guardian approval recorded.");
      await load();
    } catch (cause) {
      setError(cause.message || "The invitation could not be approved.");
    } finally { setBusy(false); }
  };

  if (!data && !error) return <div className="a11-workspace"><Loading /></div>;

  return (
    <div className="a11-workspace">
      <header>
        <p className="a11-kicker">Account and guardian operations</p>
        <h2>Learning account settings</h2>
        <p>These controls do not reveal passwords or private AI conversations. Provider-dependent independent verification and recovery remain unavailable.</p>
      </header>
      {error && <Alert kind="err">{error}</Alert>}
      {notice && <Alert>{notice}</Alert>}
      {role === "school_admin" && data?.summary && (
        <>
          <Card title="School learning summary">
            <div className="a11-stats">
              <span><b>{data.summary.learner_count}</b> learner accounts</span>
              <span><b>{data.summary.active_account_count}</b> active</span>
              <span><b>{data.summary.suspended_account_count}</b> suspended</span>
              <span><b>{data.summary.participation_count}</b> path participations</span>
            </div>
            <p className="a11-caption">Aggregate learning activity only. Independent public learner data is not included.</p>
          </Card>
          <Card title="School-managed accounts">
            {data.accountsTruncated && <Alert kind="warn">This list is capped at 200 learners. Additional accounts are not shown here.</Alert>}
            {!data.accounts.length ? <EmptyState title="No learner accounts" text="School-linked learning accounts will appear here." /> : (
              <div className="a11-list">
                {data.accounts.map((row) => (
                  <article className="a11-row" key={row.profile_id}>
                    <div><b>{row.student_name}</b><small>Age band: {row.age_band} · Guardian consent: {row.consent_state} · State: {row.account_status}</small></div>
                    <Button kind={row.account_status === "suspended" ? "secondary" : "danger"} busy={busy}
                      disabled={row.account_status === "pending_deletion" || row.account_status === "closed"}
                      onClick={() => changeSchoolAccount(row)}>
                      {row.account_status === "suspended" ? "Restore learning access" : "Suspend learning access"}
                    </Button>
                  </article>
                ))}
              </div>
            )}
          </Card>
          <Card title="Issue a school invitation">
            <p className="a11-caption">Only active roster learners without a learning account or open invitation are listed. Under-18 or unknown-age invitations require approval from that learner’s linked Marian guardian. No email or SMS is sent.</p>
            {data.candidatesTruncated && <Alert kind="warn">This candidate list is capped at 200 learners. Narrow the school roster or use the protected school invitation API for other eligible learners.</Alert>}
            {!data.candidates.length ? <EmptyState title="No eligible learners in this list" text="There are no active unlinked roster learners without an open invitation in the first 200 sorted results." /> : (
              <div className="a11-form-row">
                <label className="a11-field" htmlFor="a11-invite-student">
                  Learner
                  <select id="a11-invite-student" value={selectedStudentId} onChange={(event) => setSelectedStudentId(event.target.value)}>
                    <option value="">Select a learner</option>
                    {data.candidates.map((student) => (
                      <option key={student.student_id} value={student.student_id}
                        disabled={student.guardian_required && !student.guardian_available}>
                        {student.student_name} · {student.age_band}{guardianCandidateLabel(student)}
                      </option>
                    ))}
                  </select>
                </label>
                <Button kind="teal" busy={busy} disabled={!selectedStudentId} onClick={issueInvitation}>Create invitation</Button>
              </div>
            )}
            {issuedInvitation?.claim_token && (
              <div className="a11-one-time-code" role="status">
                <b>One-time claim code — shown only now</b>
                <p>{issuedInvitation.claim_token_delivery}</p>
                <code>{issuedInvitation.claim_token}</code>
                <p className="a11-caption">Keep this code private. It is not stored in the invitation list and Marian did not deliver it.</p>
                <Button kind="secondary" onClick={() => setIssuedInvitation(null)}>Hide code</Button>
              </div>
            )}
          </Card>
          <Card title="School invitations">
            <p className="a11-caption">Delivery-status checks are informational only. No message is sent and no code is changed. Revoke an unclaimed code if it should no longer work.</p>
            {data.invitationsTruncated && <Alert kind="warn">This invitation list is capped at 200 rows.</Alert>}
            {!data.invitations.length ? <EmptyState title="No invitations" text="School invitations will appear here." /> : (
              <div className="a11-list">
                {data.invitations.map((invitation) => {
                  const expired = new Date(invitation.expires_at).getTime() <= Date.now();
                  const state = invitation.claimed_at ? "Claimed" : invitation.revoked_at ? "Revoked" : expired ? "Expired" : "Open";
                  const canCheck = state === "Open";
                  const canRevoke = state === "Open" || state === "Expired";
                  return <article className="a11-row" key={invitation.id}>
                    <div><b>{invitation.student_name} · {state}</b><small>Guardian approval: {invitation.guardian_approval_state} · Delivery: {invitation.delivery_status} · Expires {new Date(invitation.expires_at).toLocaleString()}</small></div>
                    <div className="a11-actions">
                      {canCheck && <Button kind="secondary" busy={busy} onClick={() => checkInvitationDelivery(invitation)}>Check delivery status</Button>}
                      {canRevoke && <Button kind="danger" busy={busy} onClick={() => revokeInvitation(invitation)}>Revoke code</Button>}
                    </div>
                  </article>;
                })}
              </div>
            )}
          </Card>
        </>
      )}
      {role === "parent" && data?.learners && (
        <>
          <Card title="Pending school invitations">
            <p className="a11-caption">Only requests for active students linked to your Marian guardian account are shown. Approval records consent for the school invitation; it does not verify age or activate an unknown-age learner.</p>
            {data.guardianInvitationsTruncated && <Alert kind="warn">This invitation list is capped at 100 rows.</Alert>}
            {!data.guardianInvitations.length ? <EmptyState title="No pending invitations" text="A school invitation requiring your approval will appear here if it is linked to your guardian account." /> : (
              <div className="a11-list">
                {data.guardianInvitations.map((invitation) => (
                  <article className="a11-row" key={invitation.id}>
                    <div><b>{invitation.student_name}</b><small>Expires {new Date(invitation.expires_at).toLocaleString()}</small></div>
                    <Button kind="teal" busy={busy} onClick={() => approveGuardianInvitation(invitation)}>Approve invitation</Button>
                  </article>
                ))}
              </div>
            )}
          </Card>
          <Card title="Linked learners">
            {!data.learners.length ? <EmptyState title="No linked learning accounts" text="Only learners linked to your active Marian guardian account are shown." /> : (
              <div className="a11-list">
                {data.learners.map((row) => (
                  <article className="a11-row" key={row.profile_id}>
                    <div><b>{row.learner_name || "Independent learner"}</b><small>Age band: {row.age_band} · Consent: {row.consent_state} · Learning: {row.account_status}</small></div>
                    {row.consent_state !== "withdrawn" && <Button kind="danger" busy={busy}
                      onClick={() => withdrawConsent(row.profile_id)}>Withdraw consent</Button>}
                  </article>
                ))}
              </div>
            )}
            <p className="a11-caption">New independent guardian identity verification and consent grants are unavailable until a real provider is integrated.</p>
          </Card>
        </>
      )}
      {isLearner(role) && data && (
        <>
          <Card title="Personalized Learning plan">
            <p>Personalized Learning is an individual add-on; school fees and school subscriptions do not cover it. Any future school link for teacher recommendations is separate and is not available yet.</p>
            {data.subscription ? (
              <p>Current entitlement: <b>{data.subscription.plan_name}</b> · Tier: <b>{data.subscription.tier}</b> · Status: <b>{data.subscription.subscription_status}</b>{data.subscription.period_end ? ` · Through ${new Date(data.subscription.period_end).toLocaleDateString()}` : ""}</p>
            ) : <p>Plan status is unavailable until an eligible learning profile is assigned. Free is the default; no payment is taken.</p>}
            <p className="a11-caption">Premium checkout requires a real payment adapter and verified provider confirmation. No AI tutoring requests are enabled in this build.</p>
            <Button kind="secondary" disabled>Upgrade unavailable</Button>
          </Card>
          <Card title="Your learning account">
            {data.profile ? (
              <p>Account category: <b>{data.profile.profile.account_kind === "school_student" ? "School-managed learner" : "Independent learner"}</b> · Age band: <b>{data.profile.profile.age_band}</b> · Consent: <b>{data.profile.profile.consent_state}</b></p>
            ) : <p>Protected learning access is unavailable or your age/consent status still needs verification. Marian login remains separate from learning-feature eligibility.</p>}
            <p className="a11-caption">Activity 11 does not add independent-account or guardian-/school-assisted recovery. Existing Marian password recovery and authentication remain unchanged.</p>
          </Card>
          <Card title="Request account action">
            <p>Suspension or deletion requests block protected learning access immediately. Requests are reviewed under a future retention policy; this screen never deletes an account or academic record.</p>
            <div className="a11-actions">
              <Button kind="secondary" busy={busy} onClick={() => submitLifecycle("suspension")}>Request suspension</Button>
              <Button kind="danger" busy={busy} onClick={() => submitLifecycle("deletion")}>Request deletion</Button>
            </div>
            <div className="a11-list">
              {(data.requests || []).map((row) => (
                <article className="a11-row" key={row.id}>
                  <div><b>{row.request_type} request · {row.status}</b><small>Created {new Date(row.created_at).toLocaleString()}</small></div>
                  {row.status === "pending" && <Button kind="secondary" busy={busy} onClick={() => cancelLifecycle(row.id)}>Cancel request</Button>}
                </article>
              ))}
            </div>
          </Card>
        </>
      )}
      {data?.unavailable && <Alert kind="warn">This Marian role does not have an Activity 11 account screen.</Alert>}
    </div>
  );
}
