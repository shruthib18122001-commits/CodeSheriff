import { getGithubLoginUrl } from "../lib/api";

const FEATURES = [
  {
    icon: "💬",
    color: "#2979FF",
    title: "Codebase Q&A",
    description:
      "Ask natural language questions like \"where is auth handled?\" and get grounded answers with cited file paths and line numbers.",
  },
  {
    icon: "🗺️",
    color: "#FF6D00",
    title: "Architecture Map",
    description:
      "An interactive dependency graph of your codebase's modules, generated automatically from the indexed source.",
  },
  {
    icon: "⚠️",
    color: "#E53935",
    title: "Drift Detection",
    description:
      "Flags places where your README or docs claim something the actual code no longer reflects, so docs stay honest.",
  },
];

const PLANS = [
  {
    name: "Free",
    price: "$0",
    features: ["1 connected repo", "50 queries / month", "Codebase Q&A", "Community support"],
  },
  {
    name: "Pro",
    price: "$19",
    featured: true,
    features: ["5 connected repos", "500 queries / month", "Architecture map", "Drift detection", "Email support"],
  },
  {
    name: "Team",
    price: "$49",
    features: ["Unlimited repos", "2,000 queries / month", "Architecture map", "Drift detection", "Priority support"],
  },
];

function Landing() {
  async function handleLogin() {
    const url = await getGithubLoginUrl();
    window.location.href = url;
  }

  return (
    <div className="landing">
      <div className="landing-nav">
        <div className="brand">
          Code<span className="brand-mark">Sheriff</span>
        </div>
        <button className="btn btn-primary" onClick={handleLogin}>
          Sign in with GitHub
        </button>
      </div>

      <section className="hero">
        <h1>Talk to your codebase like a senior engineer</h1>
        <p>
          Connect a GitHub repo and ask natural language questions about it — where auth is
          handled, what would break if you change a schema, how a service handles errors.
        </p>
        <button className="btn btn-primary" onClick={handleLogin}>
          Sign in with GitHub
        </button>
      </section>

      <section className="feature-grid">
        {FEATURES.map((f) => (
          <button className="feature-card" key={f.title} onClick={handleLogin}>
            <div className="icon" style={{ background: `${f.color}22`, color: f.color }}>
              {f.icon}
            </div>
            <h3>{f.title}</h3>
            <p>{f.description}</p>
          </button>
        ))}
      </section>

      <h2 className="section-title">Pricing</h2>
      <p className="section-subtitle">Start free. Upgrade when you need more repos or queries.</p>

      <div className="pricing-grid">
        {PLANS.map((plan) => (
          <div className={`pricing-card${plan.featured ? " featured" : ""}`} key={plan.name}>
            <h3>{plan.name}</h3>
            <div className="pricing-price">
              {plan.price}
              <span>/mo</span>
            </div>
            <ul>
              {plan.features.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
            <button className={`btn ${plan.featured ? "btn-primary" : "btn-outline"}`} onClick={handleLogin}>
              {plan.name === "Free" ? "Get started" : `Choose ${plan.name}`}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

export default Landing;
