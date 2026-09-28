import { FormEvent, useEffect, useMemo, useState } from "react";
import { NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { ChatMessage, Service, Stats, User, api, bytes, pct, watts } from "./api";

const NAV = [
  ["/", "Home"],
  ["/services", "Services"],
  ["/llms", "LLMs"],
  ["/websites", "Websites"],
  ["/minecraft", "Minecraft"],
  ["/media", "Media"],
  ["/files", "Files"],
  ["/git", "Git"],
  ["/collaboration", "Collaboration"],
  ["/notifications", "Notifications"],
  ["/chat", "Chat"],
  ["/processes", "Processes"],
  ["/logs", "Logs"],
  ["/admin", "Admin"],
] as const;

export default function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    api.me().then(setUser).catch(() => setUser(null));
  }, []);

  useEffect(() => {
    if (!user) return;
    const pull = () => api.stats().then(setStats).catch(() => undefined);
    pull();
    const timer = window.setInterval(pull, 5000);
    return () => window.clearInterval(timer);
  }, [user]);

  if (user === undefined) {
    return <main className="grid min-h-screen place-items-center text-muted">Loading</main>;
  }
  if (user === null) {
    return <SignIn />;
  }

  const items = NAV.filter(([, label]) => user.admin || !["Logs", "Admin"].includes(label));

  return (
    <div className="min-h-screen md:grid md:grid-cols-[220px_1fr]">
      <aside className="border-b border-line bg-panel/80 px-4 py-5 md:min-h-screen md:border-b-0 md:border-r">
        <div className="font-serif text-2xl tracking-tight">The Server</div>
        <p className="mt-1 text-sm text-muted">{user.display_name}</p>
        <nav className="mt-6 flex gap-2 overflow-auto md:block md:space-y-1">
          {items.map(([path, label]) => (
            <NavLink
              key={path}
              to={path}
              end={path === "/"}
              className={({ isActive }) =>
                `block whitespace-nowrap rounded-full px-3 py-1.5 text-sm ${isActive ? "bg-brass text-ink" : "text-paper/80 hover:bg-white/5"}`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <button
          className="mt-6 text-sm text-muted underline decoration-line underline-offset-4"
          onClick={() => api.logout().then(() => window.location.assign("/"))}
        >
          Sign out
        </button>
      </aside>
      <div>
        <StatusBar stats={stats} />
        <main className="mx-auto max-w-5xl px-5 py-6">
          <Routes>
            <Route path="/" element={<Home user={user} />} />
            <Route path="/services" element={<Services />} />
            <Route path="/llms" element={<Llms admin={user.admin} />} />
            <Route path="/websites" element={<Websites />} />
            <Route path="/minecraft" element={<Minecraft admin={user.admin} />} />
            <Route path="/media" element={<LinkPage title="Media" linkKey="media" copy="Jellyfin streams movies, shows, music, and photos from the bulk disk." />} />
            <Route path="/files" element={<LinkPage title="Files" linkKey="files" copy="Nextcloud holds documents and shared files. Large libraries live on the bay SSD." />} />
            <Route path="/git" element={<LinkPage title="Git" linkKey="git" copy="Forgejo is the private git server. Clone over HTTPS." />} />
            <Route path="/collaboration" element={<Collaboration />} />
            <Route path="/notifications" element={<Notifications />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/processes" element={<Processes />} />
            <Route path="/logs" element={user.admin ? <Logs /> : <Denied />} />
            <Route path="/admin" element={user.admin ? <Admin /> : <Denied />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

function SignIn() {
  const failed = new URLSearchParams(window.location.search).get("auth") === "failed";
  return (
    <main className="grid min-h-screen place-items-center px-6">
      <div className="max-w-md">
        <p className="text-sm uppercase tracking-[0.2em] text-brass">Private cloud</p>
        <h1 className="mt-3 font-serif text-6xl leading-none">The Server</h1>
        <p className="mt-4 text-muted">
          Sign in with your own account. New people need a referral code from an administrator.
        </p>
        {failed && <p className="mt-4 text-clay">Sign-in did not complete. Try again once Authentik is up.</p>}
        <a href="/api/auth/login" className="mt-8 inline-block rounded-full bg-brass px-5 py-2 font-medium text-ink">
          Sign in
        </a>
      </div>
    </main>
  );
}

function StatusBar({ stats }: { stats: Stats | null }) {
  const parts = [
    ["CPU", pct(stats?.cpu ?? null)],
    ["RAM", pct(stats?.ram ?? null)],
    ["GPU", pct(stats?.gpu ?? null)],
    ["Storage", pct(stats?.storage ?? null)],
    ["Power", watts(stats?.power ?? null)],
  ];
  return (
    <div className="border-b border-line px-5 py-2 font-mono text-xs text-muted">
      {parts.map(([label, value], index) => (
        <span key={label}>
          {index > 0 && <span className="px-2 text-line">|</span>}
          {label} <span className="text-paper">{value}</span>
        </span>
      ))}
    </div>
  );
}

function Home({ user }: { user: User }) {
  return (
    <section>
      <h1 className="font-serif text-4xl">Hello, {user.display_name}</h1>
      <p className="mt-2 max-w-2xl text-muted">
        Apps, chat, media, and models use this site. Machine administration uses SSH over Tailscale.
      </p>
      <Services compact />
    </section>
  );
}

function Services({ compact = false }: { compact?: boolean }) {
  const [rows, setRows] = useState<Service[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    api.services().then((data) => setRows(data.services)).catch((err: Error) => setError(err.message));
  }, []);
  const visible = compact ? rows.filter((row) => row.state === "running").slice(0, 6) : rows;
  return (
    <section className={compact ? "mt-8" : ""}>
      {!compact && <h1 className="font-serif text-4xl">Services</h1>}
      {error && <p className="mt-3 text-clay">{error}</p>}
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {visible.map((row) => (
          <article key={row.container} className="rounded-2xl border border-line bg-panel p-4">
            <div className="flex items-center justify-between gap-3">
              <h2 className="font-medium">{row.name}</h2>
              <span className={row.state === "running" ? "text-moss" : "text-muted"}>{row.state}</span>
            </div>
            <p className="mt-2 text-sm text-muted">{row.description}</p>
            {row.url && (
              <a className="mt-3 inline-block text-sm text-brass" href={row.url}>
                Open
              </a>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}

function Llms({ admin }: { admin: boolean }) {
  const [status, setStatus] = useState<{ model: string | null; configured: boolean; manager_model?: string | null; manager_configured?: boolean } | null>(null);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  useEffect(() => {
    api.llmStatus().then(setStatus).catch((err: Error) => setError(err.message));
  }, []);

  async function ask(event: FormEvent) {
    event.preventDefault();
    const content = input.trim();
    if (!content) return;
    const next = [...messages, { role: "user", content }];
    setMessages(next);
    setInput("");
    setPending(true);
    setError("");
    try {
      const reply = await api.llmChat(next);
      setMessages([...next, { role: "assistant", content: reply.content }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The model did not answer");
    } finally {
      setPending(false);
    }
  }

  return (
    <section>
      <h1 className="font-serif text-4xl">LLMs</h1>
      <p className="mt-2 text-muted">
        {status?.configured ? `General chat model: ${status.model}` : "No model is loaded yet. An administrator starts one from the server."}
      </p>
      <p className="mt-2 max-w-2xl text-sm text-muted">
        The model can read the status numbers on this server. It cannot run commands or change the machine. Long prompts go through LLMLingua first.
      </p>
      <div className="mt-4 space-y-3">
        {messages.map((message, index) => (
          <p key={index} className="rounded-2xl border border-line bg-panel p-3">
            <span className="text-brass">{message.role === "user" ? "You" : "Model"}</span>
            <span className="mt-1 block whitespace-pre-wrap">{message.content}</span>
          </p>
        ))}
      </div>
      <form onSubmit={ask} className="mt-4 flex gap-2">
        <input className="field" value={input} onChange={(event) => setInput(event.target.value)} placeholder="Ask the local model" />
        <button className="btn" disabled={pending}>Send</button>
      </form>
      {error && <p className="mt-3 text-clay">{error}</p>}
      {admin && status?.manager_configured && <ManagerChat model={status.manager_model || ""} />}
      {admin && <KillSwitch />}
    </section>
  );
}

function ManagerChat({ model }: { model: string }) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function ask(event: FormEvent) {
    event.preventDefault();
    const content = input.trim();
    if (!content) return;
    const next = [...messages, { role: "user", content }];
    setMessages(next);
    setInput("");
    setPending(true);
    setError("");
    try {
      const reply = await api.llmManager(next);
      setMessages([...next, { role: "assistant", content: reply.content }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The manager model did not answer");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mt-8 rounded-2xl border border-line p-4">
      <h2 className="font-medium">Server manager</h2>
      <p className="mt-1 text-sm text-muted">Model {model}. It can read the status numbers and recommend a next step. It cannot change the machine.</p>
      <div className="mt-3 space-y-2">
        {messages.map((message, index) => (
          <p key={index} className="rounded-2xl border border-line bg-panel p-3">
            <span className="text-brass">{message.role === "user" ? "You" : "Manager"}</span>
            <span className="mt-1 block whitespace-pre-wrap">{message.content}</span>
          </p>
        ))}
      </div>
      <form onSubmit={ask} className="mt-3 flex gap-2">
        <input className="field" value={input} onChange={(event) => setInput(event.target.value)} placeholder="Ask about load, crashes, or cleanup" />
        <button className="btn" disabled={pending}>Send</button>
      </form>
      {error && <p className="mt-2 text-clay">{error}</p>}
    </div>
  );
}

function KillSwitch() {
  const [note, setNote] = useState("");
  return (
    <div className="mt-8 rounded-2xl border border-clay/40 p-4">
      <h2 className="font-medium">Stop AI containers</h2>
      <p className="mt-1 text-sm text-muted">Leaves the dashboard, files, and proxy running.</p>
      <button
        className="btn mt-3 bg-clay text-paper"
        onClick={() => api.action("llm-stop").then((result) => setNote(`Stopped: ${(result.stopped || []).join(", ") || "none"}`)).catch((err: Error) => setNote(err.message))}
      >
        Kill switch
      </button>
      {note && <p className="mt-2 text-sm">{note}</p>}
    </div>
  );
}

function Websites() {
  const [rows, setRows] = useState<{ name: string; url: string; description: string }[]>([]);
  useEffect(() => {
    api.websites().then((data) => setRows(data.websites)).catch(() => undefined);
  }, []);
  return (
    <section>
      <h1 className="font-serif text-4xl">Websites</h1>
      <div className="mt-4 space-y-3">
        {rows.map((site) => (
          <a key={site.url} href={site.url} className="block rounded-2xl border border-line bg-panel p-4">
            <div className="font-medium">{site.name}</div>
            <p className="text-sm text-muted">{site.description}</p>
          </a>
        ))}
      </div>
    </section>
  );
}

function Minecraft({ admin }: { admin: boolean }) {
  const [logs, setLogs] = useState("");
  const [note, setNote] = useState("");
  const [live, setLive] = useState<{ online: boolean; players: string; version: string; detail: string } | null>(null);
  const navigate = useNavigate();
  useEffect(() => {
    api.minecraftStatus().then(setLive).catch(() => undefined);
    if (!admin) return;
    api.minecraftLogs().then((data) => setLogs(data.logs || data.error || "")).catch(() => undefined);
  }, [admin]);

  function run(name: string) {
    api.action(name).then((result) => {
      if (name === "minecraft-backup" && result.file) setNote(`Saved ${result.file}`);
      else setNote("Sent.");
    }).catch((err: Error) => setNote(err.message));
  }

  return (
    <section>
      <h1 className="font-serif text-4xl">Minecraft</h1>
      <p className="mt-2 text-muted">The world is stored on the bulk disk. The game port is 25565 when that profile is enabled.</p>
      <p className="mt-3 text-sm">
        {live?.online ? live.players || "Online" : live?.detail || "The game server is not running."}
        {live?.version ? ` ${live.version}` : ""}
      </p>
      {admin && (
        <div className="mt-4 flex flex-wrap gap-2">
          <button className="btn" onClick={() => run("minecraft-start")}>Start</button>
          <button className="btn" onClick={() => run("minecraft-stop")}>Stop</button>
          <button className="btn" onClick={() => run("minecraft-restart")}>Restart</button>
          <button className="btn" onClick={() => run("minecraft-backup")}>Backup</button>
        </div>
      )}
      {note && <p className="mt-3 text-sm">{note}</p>}
      {admin && <pre className="mt-4 max-h-80 overflow-auto rounded-2xl bg-black/40 p-4 text-xs text-moss">{logs || "No console output yet."}</pre>}
      {!admin && <p className="mt-4 text-sm text-muted">Start, stop, and the console are administrator actions.</p>}
      <button className="mt-4 text-sm text-brass" onClick={() => navigate("/services")}>Service status</button>
    </section>
  );
}

function Collaboration() {
  const [links, setLinks] = useState<Record<string, string>>({});
  useEffect(() => {
    api.links().then(setLinks).catch(() => undefined);
  }, []);
  return (
    <section>
      <h1 className="font-serif text-4xl">Collaboration</h1>
      <p className="mt-2 max-w-2xl text-muted">
        Nextcloud stores the files. Collabora opens documents and spreadsheets in the browser.
      </p>
      <div className="mt-4 flex flex-wrap gap-3">
        {links.files ? <a className="btn" href={links.files}>Files</a> : <p className="text-sm text-muted">Files link appears after the domain is set and the collab profile is on.</p>}
        {links.office ? <a className="btn" href={links.office}>Office</a> : null}
      </div>
    </section>
  );
}

function LinkPage({ title, linkKey, copy }: { title: string; linkKey: string; copy: string }) {
  const [href, setHref] = useState("");
  useEffect(() => {
    api.links().then((links) => setHref(links[linkKey] || "")).catch(() => undefined);
  }, [linkKey]);
  return (
    <section>
      <h1 className="font-serif text-4xl">{title}</h1>
      <p className="mt-2 max-w-2xl text-muted">{copy}</p>
      {href ? (
        <a className="btn mt-5 inline-block" href={href}>Open</a>
      ) : (
        <p className="mt-5 text-sm text-muted">The public name is not set yet, or this service is still off.</p>
      )}
    </section>
  );
}

function Notifications() {
  const [href, setHref] = useState("");
  useEffect(() => {
    api.links().then((links) => setHref(links.notify || "")).catch(() => undefined);
  }, []);
  return (
    <section>
      <h1 className="font-serif text-4xl">Notifications</h1>
      {href && <a className="mt-2 inline-block text-brass" href={href}>Open ntfy</a>}
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <article className="rounded-2xl border border-line bg-panel p-4">
          <h2>Admin</h2>
          <p className="mt-2 text-sm text-muted">Logins, disk, model incidents, crashes, and shutdowns. This topic requires the administrator ntfy account.</p>
        </article>
        <article className="rounded-2xl border border-line bg-panel p-4">
          <h2>General</h2>
          <p className="mt-2 text-sm text-muted">Maintenance, downtime, and game nights. Anyone can read it. Only administrators can post.</p>
        </article>
      </div>
    </section>
  );
}

function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [body, setBody] = useState("");
  const [days, setDays] = useState(90);
  const known = useMemo(() => new Set(messages.map((message) => message.id)), [messages]);

  useEffect(() => {
    api.chat().then((data) => {
      setMessages(data.messages);
      setDays(data.retention_days);
    }).catch(() => undefined);
    const socket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/ws`);
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      if (payload.type !== "chat") return;
      setMessages((current) => (current.some((item) => item.id === payload.message.id) ? current : [...current, payload.message]));
    };
    return () => socket.close();
  }, []);

  async function send(event: FormEvent) {
    event.preventDefault();
    const text = body.trim();
    if (!text) return;
    setBody("");
    const message = await api.sendChat(text);
    setMessages((current) => (current.some((item) => item.id === message.id) ? current : [...current, message]));
  }

  return (
    <section>
      <h1 className="font-serif text-4xl">Chat</h1>
      <p className="mt-2 text-sm text-muted">Messages stay with your account for {days} days.</p>
      <div className="mt-4 space-y-2">
        {messages.map((message) => (
          <p key={message.id} className="rounded-2xl border border-line px-3 py-2">
            <span className="text-brass">{message.username}</span> <span className="text-xs text-muted">{message.at}</span>
            <span className="mt-1 block">{message.body}</span>
          </p>
        ))}
      </div>
      <form onSubmit={send} className="mt-4 flex gap-2">
        <input className="field" value={body} onChange={(event) => setBody(event.target.value)} placeholder="Message the server" />
        <button className="btn">Send</button>
      </form>
      <span className="hidden">{known.size}</span>
    </section>
  );
}

function Denied() {
  return (
    <section>
      <h1 className="font-serif text-4xl">Administrators only</h1>
      <p className="mt-2 text-muted">This page is limited to the administrators group.</p>
    </section>
  );
}

function Processes() {
  const [rows, setRows] = useState<{ name: string; cpu: number; ram_bytes: number }[]>([]);
  useEffect(() => {
    api.processes().then((data) => setRows(data.processes)).catch(() => undefined);
  }, []);
  return (
    <section>
      <h1 className="font-serif text-4xl">Processes</h1>
      <div className="mt-4 overflow-auto rounded-2xl border border-line">
        <table className="w-full text-left text-sm">
          <thead className="text-muted">
            <tr>
              <th className="px-3 py-2">Process</th>
              <th className="px-3 py-2">CPU</th>
              <th className="px-3 py-2">RAM</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.name} className="border-t border-line">
                <td className="px-3 py-2">{row.name}</td>
                <td className="px-3 py-2">{row.cpu}%</td>
                <td className="px-3 py-2">{bytes(row.ram_bytes)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Logs() {
  const [rows, setRows] = useState<{ id: number; at: string; actor: string; event: string; detail: string }[]>([]);
  const [href, setHref] = useState("");
  useEffect(() => {
    api.audit().then((data) => setRows(data.events)).catch(() => undefined);
    api.links().then((links) => setHref(links.grafana || "")).catch(() => undefined);
  }, []);
  return (
    <section>
      <h1 className="font-serif text-4xl">Logs</h1>
      {href && <a className="mt-2 inline-block text-brass" href={href}>Open Grafana</a>}
      <div className="mt-4 space-y-2">
        {rows.map((row) => (
          <p key={row.id} className="rounded-xl border border-line px-3 py-2 text-sm">
            <span className="text-muted">{row.at}</span> <span className="text-brass">{row.actor}</span> {row.event}
            {row.detail && <span className="mt-1 block text-muted">{row.detail}</span>}
          </p>
        ))}
      </div>
    </section>
  );
}

function Admin() {
  const [referrals, setReferrals] = useState<Record<string, string | number | null>[]>([]);
  const [role, setRole] = useState("user");
  const [note, setNote] = useState("");
  const [issued, setIssued] = useState("");
  const [error, setError] = useState("");
  const [form, setForm] = useState({ username: "", name: "", email: "", password: "" });

  function refresh() {
    api.referrals().then((data) => setReferrals(data.referrals)).catch((err: Error) => setError(err.message));
  }
  useEffect(refresh, []);

  return (
    <section>
      <h1 className="font-serif text-4xl">Admin</h1>
      <p className="mt-2 max-w-2xl text-muted">
        The first administrator was created when the server was set up. Create any other founding admins here. Everyone else gets a referral code that stays tied to the admin who issued it.
      </p>
      <form
        className="mt-6 grid gap-2 sm:grid-cols-2"
        onSubmit={(event) => {
          event.preventDefault();
          api.createReferral(role, note).then((result) => {
            setIssued(result.signup_url);
            setNote("");
            refresh();
          }).catch((err: Error) => setError(err.message));
        }}
      >
        <select className="field" value={role} onChange={(event) => setRole(event.target.value)}>
          <option value="user">Regular user</option>
          <option value="administrator">Administrator</option>
        </select>
        <input className="field" value={note} placeholder="Note" onChange={(event) => setNote(event.target.value)} />
        <button className="btn sm:col-span-2">Issue referral code</button>
      </form>
      {issued && <p className="mt-3 break-all font-mono text-sm text-brass">{issued}</p>}
      <div className="mt-4 space-y-2">
        {referrals.map((row) => (
          <div key={String(row.code)} className="flex items-center justify-between gap-3 rounded-xl border border-line px-3 py-2 text-sm">
            <div>
              <span className="font-mono">{row.code}</span>
              <span className="ml-2 text-muted">via {row.sponsor}</span>
              <span className="ml-2 text-muted">{row.role}</span>
              {row.used_by && <span className="ml-2 text-moss">used by {row.used_by}</span>}
              {row.revoked_at && <span className="ml-2 text-clay">revoked</span>}
            </div>
            {!row.revoked_at && (
              <button className="text-clay" onClick={() => api.revokeReferral(String(row.code)).then(refresh)}>
                Revoke
              </button>
            )}
          </div>
        ))}
      </div>
      <h2 className="mt-10 font-serif text-2xl">Founding administrator</h2>
      <form
        className="mt-3 grid gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          api.createAdmin(form).then(() => setForm({ username: "", name: "", email: "", password: "" })).catch((err: Error) => setError(err.message));
        }}
      >
        <input className="field" placeholder="Username" value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} />
        <input className="field" placeholder="Name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
        <input className="field" placeholder="Email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} />
        <input className="field" placeholder="Password" type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} />
        <button className="btn">Create administrator</button>
      </form>
      {error && <p className="mt-3 text-clay">{error}</p>}
      <KillSwitch />
    </section>
  );
}
