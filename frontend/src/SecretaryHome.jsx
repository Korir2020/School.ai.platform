import { useEffect, useState } from "react";
import { api } from "./api";
import SecretaryDashboard from "./SecretaryDashboard";

// Secretary Home: the user's own notices and the Connect unread counts only.
// No dashboard or finance endpoint is called from here.
const read = async (path) => {
  try {
    const r = await api(path);
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
};

export default function SecretaryHome({ me, onNavigate }) {
  const [data, setData] = useState({ channels: null, notices: null });
  useEffect(() => {
    let live = true;
    Promise.all([read("/api/connect/channels/"), read("/api/announcements/")]).then(
      ([channels, notices]) => {
        if (live) setData({ channels, notices });
      }
    );
    return () => {
      live = false;
    };
  }, []);
  return (
    <SecretaryDashboard
      me={me}
      data={data}
      onNavigate={onNavigate}
      onViewNotice={() => onNavigate("Connect")}
    />
  );
}
