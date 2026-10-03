import Logo from "./Logo";
import Scene from "./Scene";
import "./welcome.css";

export default function Welcome({ onStart }) {
  return (<div className="welcome"><Scene />
    <div className="wc"><Logo size={92} /><h1>MARIAN</h1><p className="tag">Intelligent School Management</p>
      <button className="go" onClick={onStart}>Log in</button></div></div>);
}
