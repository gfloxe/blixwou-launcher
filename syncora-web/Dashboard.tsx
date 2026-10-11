"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft, ArrowRight, Check, ChevronRight, CircleAlert, Clock3, FileArchive, FolderGit2, GitBranch, GitCompareArrows,
  HardDrive, History, LayoutGrid, LoaderCircle, RefreshCw, Search, Server,
  Settings2, Sparkles, Trash2, UploadCloud, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Toaster } from "@/components/ui/sonner";
import { toast } from "sonner";

type Destination = "github" | "server";
type UploadTarget = "github" | "server" | "both";
type PendingFile = { file: File; name: string; size: string; target: UploadTarget };
const MAX_FILE_SIZE_MB = 50;
const MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024;
type HistoryItem = { id: number; name: string; version: string; time: string; size: string; destinations: Destination[]; status: "ok" | "syncing" };
type SyncFile = { name: string; githubSize: number | null; serverSize: number | null; status: "synced" | "github_only" | "server_only" | "different" };
type ReplacementSuggestion = { key: string; baseName: string; current: SyncFile; next: SyncFile; currentVersion: string; nextVersion: string };

function versionParts(name: string) {
  const stem = name.replace(/\.(jar|zip)$/i, "");
  const matches = [...stem.matchAll(/(?:^|[-_ ])v?(\d+(?:\.\d+)+)/gi)];
  if (!matches.length) return null;
  const baseName = stem.slice(0, matches[0].index ?? 0).replace(/[-_ ]+$/, "").trim();
  if (!baseName) return null;
  return { baseName, versions: matches.map((match) => match[1]) };
}

function suggestionVersions(currentName: string, nextName: string) {
  const current = versionParts(currentName)?.versions ?? [];
  const next = versionParts(nextName)?.versions ?? [];
  const differingIndex = current.findIndex((version, index) => version !== next[index]);
  const index = differingIndex >= 0 ? differingIndex : Math.max(current.length, next.length) - 1;
  return { currentVersion: current[index] ?? current.at(-1) ?? "ancienne", nextVersion: next[index] ?? next.at(-1) ?? "nouvelle" };
}

function formatBytes(size: number | null) {
  if (size === null) return "Absent";
  return size >= 1024 * 1024 ? `${(size / 1024 / 1024).toFixed(1).replace(".", ",")} Mo` : `${Math.max(1, Math.round(size / 1024))} Ko`;
}

function DestinationBadge({ destination }: { destination: Destination }) {
  const server = destination === "server";
  return <span className={`destination-badge ${server ? "server-badge" : "github-badge"}`}>
    {server ? <Server /> : <GitBranch />}{server ? "Serveur" : "Debian"}
  </span>;
}

function Logo() {
  return <div className="brand-mark" aria-hidden="true"><span /><span /><span /></div>;
}

function HistoryRow({ item, onDelete }: { item: HistoryItem; onDelete: (id: number) => void }) {
  return <article className="history-row">
    <div className="file-icon"><FileArchive /></div>
    <div className="history-main"><div className="file-title-line"><strong>{item.name}</strong><span className="version-tag">v{item.version}</span></div><p>{item.time} <span>•</span> {item.size}</p></div>
    <div className="history-destinations">{item.destinations.map((destination) => <DestinationBadge key={destination} destination={destination} />)}</div>
    <span className={`sync-state ${item.status}`}>{item.status === "syncing" ? <LoaderCircle className="spin" /> : <Check />}{item.status === "syncing" ? "Envoi…" : "Synchronisé"}</span>
    <button className="trash-button" aria-label={`Supprimer ${item.name}`} onClick={() => onDelete(item.id)}><Trash2 /></button>
  </article>;
}

export default function Home() {
  const [destinationGithub, setDestinationGithub] = useState(true);
  const [destinationServer, setDestinationServer] = useState(true);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [activeTab, setActiveTab] = useState("dashboard");
  const [repository, setRepository] = useState("gfloxe/BLIXWOU");
  const [branch, setBranch] = useState("main");
  const [githubPath, setGithubPath] = useState("mods");
  const [serverId, setServerId] = useState("");
  const [serverPath, setServerPath] = useState("mods");
  const [connections, setConnections] = useState({ github: false, exaroton: false, githubReadOnly: false });
  const [syncFiles, setSyncFiles] = useState<SyncFile[]>([]);
  const [syncLoading, setSyncLoading] = useState(false);
  const [syncError, setSyncError] = useState("");
  const [syncingName, setSyncingName] = useState("");
  const [deletingName, setDeletingName] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [ignoredSuggestions, setIgnoredSuggestions] = useState<string[]>([]);
  const [replacingSuggestion, setReplacingSuggestion] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const autoAnalyzeRef = useRef(false);
  const analysisInFlightRef = useRef(false);

  const selectFiles = (files: File[]) => {
    const valid = files.filter((file) => /\.(jar|zip)$/i.test(file.name) && file.size <= MAX_FILE_SIZE);
    const rejected = files.length - valid.length;
    if (rejected) toast.error(`${rejected} fichier${rejected > 1 ? "s" : ""} ignoré${rejected > 1 ? "s" : ""} : format invalide ou plus de ${MAX_FILE_SIZE_MB} Mo.`);
    setPendingFiles((current) => {
      const merged = new Map(current.map((entry) => [entry.name, entry]));
      const target: UploadTarget = destinationGithub && !destinationServer ? "github" : !destinationGithub && destinationServer ? "server" : "both";
      for (const file of valid) merged.set(file.name, { file, name: file.name, size: formatBytes(file.size), target });
      return [...merged.values()];
    });
    if (fileRef.current) fileRef.current.value = "";
  };

  const upload = async () => {
    if (!pendingFiles.length) return;
    setUploading(true);
    const batchId = Date.now();
    const rows = pendingFiles.map((pending, index) => {
      const match = pending.name.match(/^(.+?)[-_ ]v?(\d+(?:\.\d+)+).*\.(jar|zip)$/i);
      const destinations: Destination[] = pending.target === "both" ? ["github", "server"] : [pending.target];
      return { id: batchId + index, name: match?.[1] ?? pending.name.replace(/\.(jar|zip)$/i, ""), version: match?.[2] ?? "nouvelle", time: "À l’instant", size: pending.size, destinations, status: "syncing" as const };
    });
    setHistory((current) => [...rows, ...current]);
    const failed = new Set<string>();
    let uploaded = 0;
    for (let index = 0; index < pendingFiles.length; index += 1) {
      const pending = pendingFiles[index]; const row = rows[index];
      const form = new FormData();
      form.set("file", pending.file); form.set("github", String(pending.target === "github" || pending.target === "both")); form.set("server", String(pending.target === "server" || pending.target === "both"));
      form.set("repository", repository); form.set("branch", branch); form.set("githubPath", githubPath); form.set("serverId", serverId); form.set("serverPath", serverPath);
      try {
        const response = await fetch("/syncora/api/sync", { method: "POST", body: form });
        const payload = await response.json() as { event?: { id: number }; error?: string; warning?: string };
        if (!response.ok) throw new Error(payload.error || "Synchronisation impossible.");
        if (payload.warning) toast.warning(payload.warning); uploaded += 1;
        setHistory((current) => current.map((item) => item.id === row.id ? { ...item, id: payload.event?.id ?? item.id, status: "ok" } : item));
      } catch (error) {
        failed.add(pending.name);
        setHistory((current) => current.filter((item) => item.id !== row.id));
        toast.error(`${pending.name} : ${error instanceof Error ? error.message : "synchronisation impossible"}`);
      }
    }
    setPendingFiles((current) => current.filter((entry) => failed.has(entry.name)));
    if (uploaded) { toast.success(`${uploaded} fichier${uploaded > 1 ? "s" : ""} synchronisé${uploaded > 1 ? "s" : ""}`); await analyzeDestinations(false); }
    setUploading(false);
  };

  useEffect(() => {
    const saved = window.localStorage.getItem("syncora-settings");
    if (saved) {
      try {
        const value = JSON.parse(saved) as { repository?: string; branch?: string; githubPath?: string; serverId?: string; serverPath?: string };
        if (["mods", "shaderpacks", "resourcepacks"].includes(value.githubPath ?? "")) setGithubPath(value.githubPath!);
        if (value.serverId) setServerId(value.serverId); if (value.serverPath) setServerPath(value.serverPath);
      } catch { /* ignore invalid local preference */ }
    }
    void fetch("/syncora/api/connections").then((response) => response.ok ? response.json() : null).then((payload: { configured?: { github: boolean; exaroton: boolean }; githubReadOnly?: boolean; servers?: Array<{ id: string }> } | null) => {
      if (payload?.configured) setConnections({ ...payload.configured, githubReadOnly: Boolean(payload.githubReadOnly) });
      if (!serverId && payload?.servers?.[0]?.id) setServerId(payload.servers[0].id);
    }).catch(() => undefined);
    void fetch("/syncora/api/history").then((response) => response.ok ? response.json() : null).then((payload: { events?: Array<{ id: number; baseName: string; version: string; size: number; github: boolean; server: boolean; status: "ok"; createdAt: string }> } | null) => {
      if (!payload?.events?.length) return;
      const formatted = payload.events.map((event) => ({ id: event.id, name: event.baseName, version: event.version, time: new Date(event.createdAt).toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }), size: event.size > 1024 * 1024 ? `${(event.size / 1024 / 1024).toFixed(1).replace(".", ",")} Mo` : `${Math.round(event.size / 1024)} Ko`, destinations: [event.github && "github", event.server && "server"].filter(Boolean) as Destination[], status: event.status }));
      setHistory(formatted);
    }).catch(() => undefined);
  // Settings are intentionally loaded once for this device.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const saveSettings = () => {
    window.localStorage.setItem("syncora-settings", JSON.stringify({ repository, branch, githubPath, serverId, serverPath }));
    toast.success("Paramètres enregistrés");
  };

  const deleteHistory = (id: number) => {
    setHistory((current) => current.filter((entry) => entry.id !== id));
    if (id < 1_000_000_000_000) void fetch(`/syncora/api/history?id=${id}`, { method: "DELETE" });
  };

  const analyzeDestinations = async (notify = true) => {
    if (analysisInFlightRef.current) return;
    analysisInFlightRef.current = true;
    setSyncLoading(true); setSyncError("");
    const query = new URLSearchParams({ repository, branch, githubPath, serverId, serverPath });
    try {
      const response = await fetch(`/syncora/api/snapshot?${query}`);
      const payload = await response.json() as { files?: SyncFile[]; error?: string; warning?: string };
      if (!response.ok) throw new Error(payload.error || "Analyse impossible.");
      setSyncFiles(payload.files ?? []);
      if (notify) toast.success("Debian et exaroton ont été comparés");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Analyse impossible.";
      setSyncError(message); if (notify) toast.error(message);
    } finally { analysisInFlightRef.current = false; setSyncLoading(false); }
  };

  useEffect(() => {
    if (!serverId || autoAnalyzeRef.current) return;
    autoAnalyzeRef.current = true;
    void analyzeDestinations(false);
  // Run once as soon as the saved server is available.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverId]);

  useEffect(() => {
    if (!serverId) return;
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") void analyzeDestinations(false);
    }, 10_000);
    return () => window.clearInterval(interval);
  // Refresh automatically when the active configuration changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repository, branch, githubPath, serverId, serverPath]);

  const reconcileFile = async (file: SyncFile, source: "github" | "server") => {
    setSyncingName(file.name); setSyncError("");
    try {
      const response = await fetch("/syncora/api/reconcile", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source, name: file.name, repository, branch, githubPath, serverId, serverPath }) });
      const payload = await response.json() as { error?: string; warning?: string };
      if (!response.ok) throw new Error(payload.error || "Synchronisation impossible.");
      toast.success(`${file.name} est maintenant identique des deux côtés`);
      await analyzeDestinations(false);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Synchronisation impossible.";
      setSyncError(message); toast.error(message);
    } finally { setSyncingName(""); }
  };

  const deleteRemoteFile = async (file: SyncFile) => {
    const destinations = [file.githubSize !== null && "Debian", file.serverSize !== null && "exaroton"].filter(Boolean).join(" et ");
    if (!window.confirm(`Supprimer définitivement ${file.name} de ${destinations} ?`)) return;
    setDeletingName(file.name); setSyncError("");
    try {
      const response = await fetch("/syncora/api/files", { method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: file.name, repository, branch, githubPath, serverId, serverPath, github: file.githubSize !== null, server: file.serverSize !== null }) });
      const payload = await response.json() as { error?: string; warning?: string };
      if (!response.ok) throw new Error(payload.error || "Suppression impossible.");
      toast.success(`${file.name} a été supprimé`);
      await analyzeDestinations(false);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Suppression impossible.";
      setSyncError(message); toast.error(message);
    } finally { setDeletingName(""); }
  };

  const filteredSyncFiles = syncFiles.filter((file) => file.name.toLocaleLowerCase("fr").includes(searchQuery.trim().toLocaleLowerCase("fr")));
  const replacementSuggestions = useMemo(() => {
    const collator = new Intl.Collator("fr", { numeric: true, sensitivity: "base" });
    const groups = new Map<string, { baseName: string; files: SyncFile[] }>();
    for (const file of syncFiles) {
      const parsed = versionParts(file.name);
      if (!parsed) continue;
      const key = parsed.baseName.toLocaleLowerCase("fr");
      const group = groups.get(key) ?? { baseName: parsed.baseName, files: [] };
      group.files.push(file); groups.set(key, group);
    }
    return [...groups.entries()].flatMap(([groupKey, group]) => {
      const files = [...group.files].sort((a, b) => collator.compare(a.name, b.name));
      if (files.length < 2) return [];
      const current = files.at(-2)!; const next = files.at(-1)!;
      const versions = suggestionVersions(current.name, next.name);
      const key = `${groupKey}:${current.name}:${next.name}`;
      if (versions.currentVersion === versions.nextVersion || ignoredSuggestions.includes(key)) return [];
      return [{ key, baseName: group.baseName, current, next, ...versions } satisfies ReplacementSuggestion];
    }).sort((a, b) => collator.compare(a.baseName, b.baseName));
  }, [syncFiles, ignoredSuggestions]);

  const applyReplacement = async (suggestion: ReplacementSuggestion) => {
    if (!window.confirm(`Remplacer ${suggestion.current.name} par ${suggestion.next.name} ? L’ancienne version sera supprimée.`)) return;
    setReplacingSuggestion(suggestion.key); setSyncError("");
    try {
      if (suggestion.next.status === "github_only" || suggestion.next.status === "server_only") {
        const source = suggestion.next.status === "github_only" ? "github" : "server";
        const syncResponse = await fetch("/syncora/api/reconcile", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source, name: suggestion.next.name, repository, branch, githubPath, serverId, serverPath }) });
        const syncPayload = await syncResponse.json() as { error?: string; warning?: string };
        if (!syncResponse.ok) throw new Error(syncPayload.error || "La nouvelle version n’a pas pu être synchronisée.");
      }
      const deleteResponse = await fetch("/syncora/api/files", { method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: suggestion.current.name, repository, branch, githubPath, serverId, serverPath, github: suggestion.current.githubSize !== null, server: suggestion.current.serverSize !== null }) });
      const deletePayload = await deleteResponse.json() as { error?: string; warning?: string };
      if (!deleteResponse.ok) throw new Error(deletePayload.error || "L’ancienne version n’a pas pu être supprimée.");
      toast.success(`${suggestion.baseName} est passé de ${suggestion.currentVersion} à ${suggestion.nextVersion}`);
      await analyzeDestinations(false);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Remplacement impossible.";
      setSyncError(message); toast.error(message);
    } finally { setReplacingSuggestion(""); }
  };

  useEffect(() => {
    const modelContext = (document as Document & { modelContext?: { registerTool?: (tool: unknown, options?: { signal?: AbortSignal }) => void | Promise<void> } }).modelContext;
    if (!modelContext?.registerTool) return;
    const lifecycle = new AbortController();
    void Promise.resolve(modelContext.registerTool({
      name: "prepare_sync", title: "Préparer une synchronisation",
      description: "Choisit Debian, le serveur exaroton, ou les deux comme destinations visibles de la prochaine synchronisation.",
      inputSchema: { type: "object", properties: { github: { type: "boolean" }, server: { type: "boolean" } }, required: ["github", "server"], additionalProperties: false },
      annotations: { readOnlyHint: false, untrustedContentHint: false },
      execute(input: unknown) {
        const value = input as { github?: unknown; server?: unknown };
        if (typeof value.github !== "boolean" || typeof value.server !== "boolean" || (!value.github && !value.server)) throw new Error("Choisissez au moins une destination.");
        setDestinationGithub(value.github); setDestinationServer(value.server); setActiveTab("dashboard");
        return { prepared: true, destinations: [value.github && "github", value.server && "server"].filter(Boolean) };
      },
    }, { signal: lifecycle.signal })).catch(() => undefined);
    return () => lifecycle.abort();
  }, []);

  return <main className="app-shell">
    <Toaster position="bottom-right" />
    <header className="topbar"><div className="brand"><Logo /><span>SYNCORA</span></div><div className="status-pill"><span /> Systèmes opérationnels</div><button className="avatar" aria-label="Profil">DJ</button></header>
    <Tabs value={activeTab} onValueChange={setActiveTab} className="workspace">
      <aside className="sidebar">
        <TabsList orientation="vertical" className="nav-list">
          <TabsTrigger value="dashboard"><LayoutGrid /> Vue d’ensemble</TabsTrigger>
          <TabsTrigger value="history"><History /> Historique <span className="count">{history.length}</span></TabsTrigger>
          <TabsTrigger value="settings"><Settings2 /> Paramètres</TabsTrigger>
        </TabsList>
        <div className="sidebar-foot"><div><span>Debian</span><b className={connections.github ? "connected-dot" : "offline-dot"} /> {connections.github ? "Connecté" : connections.githubReadOnly ? "Lecture seule" : "À configurer"}</div><div><span>exaroton</span><b className={connections.exaroton ? "connected-dot" : "offline-dot"} /> {connections.exaroton ? "Connecté" : "À configurer"}</div></div>
      </aside>
      <section className="content">
        <TabsContent value="dashboard">
          <div className="page-heading"><div><p className="eyebrow">CENTRE DE SYNCHRONISATION</p><h1>Debian ↔ exaroton</h1></div><button className="icon-button" aria-label="Analyser les destinations" onClick={() => void analyzeDestinations()}><RefreshCw className={syncLoading ? "spin" : ""} /></button></div>
          <section className="sync-card">
            <div className="destination-grid">
              <label className={`destination-choice ${destinationGithub ? "selected github-choice" : ""}`}><Checkbox checked={destinationGithub} onCheckedChange={(value) => setDestinationGithub(value === true)} aria-label="Envoyer sur Debian" /><span className="choice-icon github-icon"><GitBranch /></span><span><strong>Debian</strong><small>{githubPath}</small></span>{destinationGithub && <Check className="choice-check" />}</label>
              <label className={`destination-choice ${destinationServer ? "selected server-choice" : ""}`}><Checkbox checked={destinationServer} onCheckedChange={(value) => setDestinationServer(value === true)} aria-label="Envoyer sur exaroton" /><span className="choice-icon server-icon"><Server /></span><span><strong>Serveur exaroton</strong><small>/mods</small></span>{destinationServer && <Check className="choice-check" />}</label>
            </div>
            <div className="upload-divider"><span>envoyer de nouveaux fichiers</span></div>
            <div className={`drop-zone ${pendingFiles.length ? "has-file" : ""}`} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); selectFiles(Array.from(event.dataTransfer.files)); }}>
              <input ref={fileRef} type="file" accept=".jar,.zip" multiple onChange={(event) => selectFiles(Array.from(event.target.files ?? []))} />
              {pendingFiles.length ? <div className="pending-files"><div className="pending-files-head"><span><strong>{pendingFiles.length} fichier{pendingFiles.length > 1 ? "s" : ""} prêt{pendingFiles.length > 1 ? "s" : ""}</strong><small>JAR et ZIP • {MAX_FILE_SIZE_MB} Mo maximum par fichier</small></span><button className="add-files-button" onClick={() => fileRef.current?.click()}><UploadCloud /> Ajouter</button></div>{pendingFiles.map((pending) => <div className="pending-file" key={pending.name}><span className="pending-icon"><FileArchive /></span><div className="pending-file-info"><strong>{pending.name}</strong><p>{pending.size} • prêt à envoyer</p></div><div className="pending-targets" aria-label={`Destination de ${pending.name}`}><button className={pending.target === "github" ? "active" : ""} onClick={() => setPendingFiles((current) => current.map((entry) => entry.name === pending.name ? { ...entry, target: "github" } : entry))}><GitBranch /> Debian</button><button className={pending.target === "server" ? "active" : ""} onClick={() => setPendingFiles((current) => current.map((entry) => entry.name === pending.name ? { ...entry, target: "server" } : entry))}><Server /> exaroton</button><button className={pending.target === "both" ? "active" : ""} onClick={() => setPendingFiles((current) => current.map((entry) => entry.name === pending.name ? { ...entry, target: "both" } : entry))}>Les deux</button></div><button className="remove-pending" onClick={() => setPendingFiles((current) => current.filter((entry) => entry.name !== pending.name))} aria-label={`Retirer ${pending.name}`}><X /></button></div>)}</div> : <><span className="upload-icon"><UploadCloud /></span><h2>Déposez vos fichiers ici</h2><p>ou <button onClick={() => fileRef.current?.click()}>parcourez vos fichiers</button></p><small>Plusieurs .JAR ou .ZIP • {MAX_FILE_SIZE_MB} Mo maximum par fichier</small></>}
            </div>
            <div className="sync-actions"><p>Chaque fichier peut avoir sa propre destination</p><Button className="sync-button" size="lg" disabled={!pendingFiles.length || uploading} onClick={upload}>{uploading ? <LoaderCircle className="spin" /> : <UploadCloud />} {uploading ? "Synchronisation…" : `Synchroniser${pendingFiles.length > 1 ? ` ${pendingFiles.length} fichiers` : " maintenant"}`}</Button></div>
          </section>
          <div className="section-title"><div><Sparkles /><span><strong>Remplacements suggérés</strong><small>Versions différentes détectées dans vos fichiers</small></span></div><span className="suggestion-count">{replacementSuggestions.length} suggestion{replacementSuggestions.length > 1 ? "s" : ""}</span></div>
          <div className="suggestion-list">
            {!syncLoading && replacementSuggestions.length === 0 && <div className="suggestion-empty"><Sparkles /><span><strong>Aucun remplacement détecté</strong><small>Une suggestion apparaîtra quand deux versions du même mod seront trouvées.</small></span></div>}
            {replacementSuggestions.map((suggestion) => <article className="suggestion-card" key={suggestion.key}>
              <div className="comparison-file old-file"><FileArchive /><span><small>VERSION ACTUELLE</small><strong>{suggestion.current.name}</strong><p>{formatBytes(Math.max(suggestion.current.githubSize ?? 0, suggestion.current.serverSize ?? 0))}</p></span></div>
              <div className="version-arrow"><span>{suggestion.currentVersion}</span><ChevronRight /><span className="new-version">{suggestion.nextVersion}</span></div>
              <div className="comparison-file new-file"><FileArchive /><span><small>NOUVELLE VERSION</small><strong>{suggestion.next.name}</strong><p>{formatBytes(Math.max(suggestion.next.githubSize ?? 0, suggestion.next.serverSize ?? 0))} • prête à remplacer</p></span></div>
              <div className="suggestion-meta"><div>{suggestion.next.githubSize !== null && <DestinationBadge destination="github" />}{suggestion.next.serverSize !== null && <DestinationBadge destination="server" />}</div><button className="replace-button" onClick={() => applyReplacement(suggestion)} disabled={replacingSuggestion === suggestion.key}>{replacingSuggestion === suggestion.key ? <LoaderCircle className="spin" /> : "Remplacer"}</button><button className="trash-button" aria-label={`Ignorer la suggestion pour ${suggestion.baseName}`} title="Ignorer cette suggestion" onClick={() => setIgnoredSuggestions((current) => [...current, suggestion.key])}><Trash2 /></button></div>
            </article>)}
          </div>
          <div className="section-title inventory-title">
            <div><Clock3 /><span><strong>Tous les mods</strong><small>{syncLoading ? "Actualisation…" : `${syncFiles.length} fichier${syncFiles.length > 1 ? "s" : ""} trouvé${syncFiles.length > 1 ? "s" : ""} • mise à jour toutes les 10 s`}</small></span></div>
            <label className="mod-search"><Search /><input value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="Rechercher un mod…" aria-label="Rechercher un mod" />{searchQuery && <button onClick={() => setSearchQuery("")} aria-label="Effacer la recherche"><X /></button>}</label>
          </div>
          {syncError && <div className="sync-error inventory-error"><CircleAlert />{syncError}<button onClick={() => setActiveTab("settings")}>Ouvrir les paramètres</button></div>}
          <div className="inventory-list">
            {!syncLoading && syncFiles.length === 0 && <div className="inventory-empty">Aucun mod chargé. Lance une analyse pour actualiser la liste.</div>}
            {!syncLoading && syncFiles.length > 0 && filteredSyncFiles.length === 0 && <div className="inventory-empty">Aucun mod ne correspond à « {searchQuery} ».</div>}
            {filteredSyncFiles.map((file) => <article className="sync-file-row inventory-row" key={file.name}>
              <div className="sync-file-name"><FileArchive /><span><strong>{file.name}</strong><small>{file.status === "synced" ? "Identique des deux côtés" : file.status === "github_only" ? "Uniquement sur Debian" : file.status === "server_only" ? "Uniquement sur exaroton" : "Versions différentes"}</small></span></div>
              <div className={`side-state ${file.githubSize === null ? "missing" : ""}`}><GitBranch /><span>Debian<small>{formatBytes(file.githubSize)}</small></span></div>
              <div className="sync-link"><span className={file.status === "synced" ? "linked" : "unlinked"}>{file.status === "synced" ? <Check /> : <GitCompareArrows />}</span></div>
              <div className={`side-state ${file.serverSize === null ? "missing" : ""}`}><Server /><span>exaroton<small>{formatBytes(file.serverSize)}</small></span></div>
              <div className="sync-row-actions inventory-actions">
                {file.status !== "synced" && file.githubSize !== null && <button title="Copier Debian vers exaroton" onClick={() => reconcileFile(file, "github")} disabled={syncingName === file.name || deletingName === file.name}><GitBranch /><ArrowRight /><Server /></button>}
                {file.status !== "synced" && file.serverSize !== null && <button title="Copier exaroton vers Debian" onClick={() => reconcileFile(file, "server")} disabled={syncingName === file.name || deletingName === file.name}><Server /><ArrowLeft /><GitBranch /></button>}
                {file.status === "synced" && <span className="synced-label"><Check /> Synchronisé</span>}
                <button className="remote-trash" title={`Supprimer ${file.name}`} aria-label={`Supprimer ${file.name}`} onClick={() => deleteRemoteFile(file)} disabled={deletingName === file.name || syncingName === file.name}>{deletingName === file.name ? <LoaderCircle className="spin" /> : <Trash2 />}</button>
              </div>
            </article>)}
          </div>
        </TabsContent>
        <TabsContent value="history"><div className="page-heading"><div><p className="eyebrow">JOURNAL UNIFIÉ</p><h1>Historique des synchronisations</h1></div></div><div className="history-list full-history">{history.map((item) => <HistoryRow key={item.id} item={item} onDelete={(id) => { deleteHistory(id); toast("Entrée supprimée"); }} />)}</div></TabsContent>
        <TabsContent value="settings">
          <div className="page-heading"><div><p className="eyebrow">CONFIGURATION</p><h1>Répertoires et connexions</h1></div></div>
          <div className="settings-grid">
            <section className="settings-card"><div className="settings-card-title"><GitBranch /><div><h2>Debian</h2><p>Debian principal · GitHub en secours</p></div><span className="live-label">{connections.github ? "Connecté" : connections.githubReadOnly ? "Lecture publique" : "Jeton requis"}</span></div><label>Dépôt<input value={repository} readOnly placeholder="propriétaire/dépôt" /></label><label>Branche<input value={branch} readOnly /></label><label>Répertoire<input value={githubPath} onChange={(event) => setGithubPath(event.target.value)} /></label><div className="setting-toggle"><span><strong>Remplacer le fichier existant</strong><small>{connections.github ? "Publie sur Debian ; GitHub conserve la copie de secours" : "Un nouveau jeton sera nécessaire pour écrire sur Debian"}</small></span><Switch defaultChecked disabled={!connections.github} /></div></section>
            <section className="settings-card"><div className="settings-card-title"><Server /><div><h2>Serveur exaroton</h2><p>Destination des fichiers du serveur</p></div><span className="live-label cyan">{connections.exaroton ? "Connecté" : "Jeton requis"}</span></div><label>ID du serveur<input value={serverId} onChange={(event) => setServerId(event.target.value)} placeholder="Identifiant exaroton" /></label><label>Répertoire<input value={serverPath} onChange={(event) => setServerPath(event.target.value)} /></label><label>Sauvegarde<input defaultValue="backups/mods" /></label><div className="setting-toggle"><span><strong>Protection du remplacement</strong><small>Écrase uniquement le fichier de même nom</small></span><Switch defaultChecked /></div></section>
          </div>
          <section className="settings-card storage-card"><div className="settings-card-title"><HardDrive /><div><h2>Règles de classement</h2><p>Détection automatique du nom et de la version</p></div></div><div className="path-preview"><FolderGit2 /><code>nom-du-mod / nom-du-mod-version.jar</code></div><Button onClick={saveSettings}>Enregistrer les paramètres</Button></section>
        </TabsContent>
      </section>
    </Tabs>
  </main>;
}

