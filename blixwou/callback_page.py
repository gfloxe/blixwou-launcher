"""Self-contained OAuth return page. Never render codes, tokens or provider text."""
import base64
from .config import resource


def callback_page(status="received"):
    title, message, symbol = {
        "received": ("Retour à BLIXWOU", "La réponse Microsoft a été reçue. Le launcher vérifie maintenant votre accès à Minecraft Java.", "↗"),
        "cancelled": ("Connexion interrompue", "Microsoft n’a pas autorisé cette connexion. Revenez dans BLIXWOU pour consulter le message et réessayer.", "!"),
        "invalid": ("Ce lien a expiré", "Cette page ne correspond pas à la connexion en cours. Lancez une nouvelle tentative depuis BLIXWOU.", "!")
    }[status]
    background = base64.b64encode(resource("assets/landscape.png").read_bytes()).decode("ascii")
    return ("""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark">
<title>BLIXWOU · Connexion Microsoft</title>
<style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#100c1c;color:#faf7ff;font-family:'Segoe UI',Arial,sans-serif;padding:32px}
body:before{content:'';position:fixed;inset:0;background:linear-gradient(90deg,rgba(12,8,23,.88),rgba(12,8,23,.54)),url(data:image/png;base64,BACKGROUND) center/cover;z-index:-1}
main{width:min(960px,100%)}header{display:flex;align-items:center;gap:12px;letter-spacing:4px;font-weight:750;margin-bottom:68px}.logo{display:grid;place-items:center;width:42px;height:42px;border:1px solid #b785ff;border-radius:12px;background:#59338d;letter-spacing:0;font-size:26px}
section{max-width:660px;background:rgba(19,13,32,.88);border:1px solid #675078;border-radius:24px;padding:48px;box-shadow:0 24px 80px #09061080;backdrop-filter:blur(14px)}
.eyebrow{font-size:11px;letter-spacing:3px;color:#c6a7ef;font-weight:650}.symbol{display:grid;place-items:center;border-radius:16px;background:#9454ef24;border:1px solid #9462c7;color:#d1b2ff;width:58px;height:58px;font-size:32px;margin:26px 0}
h1{font-size:clamp(30px,5vw,46px);letter-spacing:-1.5px;line-height:1.1;margin:0 0 20px}p{font-size:17px;line-height:1.75;color:#cec4dc;margin:0}
.return{margin-top:32px;padding:18px 22px;border-radius:12px;background:#9454ef;color:white;font-weight:650;font-size:16px}.hint{margin-top:18px;font-size:13px;color:#aa9cb9}footer{font-size:11px;letter-spacing:2px;color:#b3a2c7;margin-top:34px}
@media(max-width:600px){body{padding:22px}header{margin-bottom:32px}section{padding:28px}}
</style></head><body><main><header><span class="logo">B</span> BLIXWOU</header>
<section><div class="eyebrow">CONNEXION MICROSOFT</div><div class="symbol">SYMBOL</div>
<h1>TITLE</h1><p>MESSAGE</p><div class="return">Reprenez la fenêtre BLIXWOU pour continuer ↗</div>
<p class="hint">Vous pouvez fermer cet onglet. Le résultat final s’affiche dans le launcher.</p></section>
<footer>MINECRAFT JAVA · VOTRE AVENTURE CONTINUE</footer></main>
<script>history.replaceState(null,'',location.pathname)</script></body></html>"""
            .replace("BACKGROUND", background).replace("SYMBOL", symbol)
            .replace("TITLE", title).replace("MESSAGE", message)).encode("utf-8")
