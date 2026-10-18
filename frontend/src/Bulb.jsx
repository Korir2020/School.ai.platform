import "./bulb.css";

/* Original bulb page (public/bulb.html), shown unchanged as a fixed background. */
export default function Bulb() {
  return (
    <iframe
      className="bulb-frame"
      src="/bulb.html"
      title="Background"
      aria-hidden="true"
      tabIndex={-1}
    />
  );
}
