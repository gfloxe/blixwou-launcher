import React, {useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import Dashboard from './Dashboard';
import './styles.css';

function App(){
 const [backup,setBackup]=useState<{configured:boolean;current:boolean}|null>(null);
 const [authenticated,setAuthenticated]=useState<boolean|null>(null);
 const [name,setName]=useState('admin'),[password,setPassword]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{fetch('/syncora/api/session').then(r=>r.json()).then(d=>setAuthenticated(d.authenticated)).catch(()=>{setAuthenticated(false);setError('Service indisponible');});},[]);
 useEffect(()=>{if(!authenticated)return; const refresh=()=>fetch('/syncora/api/backup').then(r=>r.json()).then(setBackup).catch(()=>setBackup(null));void refresh();const timer=setInterval(refresh,10000);return()=>clearInterval(timer);},[authenticated]);
 async function login(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');try{const r=await fetch('/syncora/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,password})});const d=await r.json();if(!r.ok)throw Error(d.error);setPassword('');setAuthenticated(true);}catch(e){setError(e instanceof Error?e.message:'Connexion impossible');}finally{setBusy(false);}}
 if(authenticated===null)return <div className="login-shell">Chargement de Syncora…</div>;
 if(authenticated)return <><div className="backup-status">GitHub secours : {backup ? (!backup.configured ? "à configurer" : backup.current ? "à jour" : "sauvegarde en attente") : "vérification…"}</div><button className="admin-logout" onClick={async()=>{await fetch('/syncora/api/logout',{method:'POST'});setAuthenticated(false);}}>Déconnexion administrateur</button><Dashboard/></>;
 return <main className="login-shell"><form className="login-card" onSubmit={login}><p className="eyebrow">BLIXWOU · ADMINISTRATION</p><h1>Syncora</h1><p>Gérez les fichiers du pack depuis Debian.<br/>GitHub reste la copie de secours.</p><label>Identifiant<input required autoComplete="username" value={name} onChange={e=>setName(e.target.value)}/></label><label>Mot de passe<input required type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)}/></label>{error&&<p role="alert" className="login-error">{error}</p>}<button disabled={busy}>{busy?'Connexion…':'Se connecter'}</button><small>Accès réservé à l’administrateur. Aucun compte joueur n’est nécessaire.</small></form></main>;
}
createRoot(document.getElementById('root')!).render(<App/>);

