import { useState } from "react";
import App from "./App";
import Splash from "./Splash";
import { ToastProvider } from "./ui";

export default function Root() {
  const [splash, setSplash] = useState(!sessionStorage.getItem("splash"));
  const done = () => { sessionStorage.setItem("splash", "1"); setSplash(false); };
  return <ToastProvider>{splash && <Splash onDone={done} />}<App /></ToastProvider>;
}
