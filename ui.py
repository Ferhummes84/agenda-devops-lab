"""
ui.py — camada puramente visual do Agenda DevOps: ícones outline (estilo
Lucide/Feather, SVG inline embutido, sem CDN) e o fundo animado "Matrix rain".

Nada aqui toca em Supabase, auth ou IA — só apresentação.
"""
import streamlit as st
import streamlit.components.v1 as components

# ---------- Ícones ----------

_ICON_PATHS = {
    "terminal": (
        '<polyline points="4 17 10 11 4 5"></polyline>'
        '<line x1="12" y1="19" x2="20" y2="19"></line>'
    ),
    "target": (
        '<circle cx="12" cy="12" r="10"></circle>'
        '<circle cx="12" cy="12" r="6"></circle>'
        '<circle cx="12" cy="12" r="2"></circle>'
    ),
    "activity": '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>',
    "git-branch": (
        '<line x1="6" y1="3" x2="6" y2="15"></line>'
        '<circle cx="18" cy="6" r="3"></circle>'
        '<circle cx="6" cy="18" r="3"></circle>'
        '<path d="M18 9a9 9 0 0 1-9 9"></path>'
    ),
    "sparkles": (
        '<path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 '
        '0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 '
        '.963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 '
        '.964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1 '
        '-.963 0z"></path>'
        '<path d="M20 3v4"></path><path d="M22 5h-4"></path>'
        '<path d="M4 17v2"></path><path d="M5 18H3"></path>'
    ),
    "user": (
        '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>'
        '<circle cx="12" cy="7" r="4"></circle>'
    ),
    "log-out": (
        '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>'
        '<polyline points="16 17 21 12 16 7"></polyline>'
        '<line x1="21" y1="12" x2="9" y2="12"></line>'
    ),
    "key": (
        '<circle cx="8" cy="8" r="4"></circle>'
        '<line x1="10.85" y1="10.85" x2="20" y2="20"></line>'
        '<line x1="15" y1="15.7" x2="18" y2="12.7"></line>'
        '<line x1="17.5" y1="18.2" x2="20" y2="15.7"></line>'
    ),
    "lock": (
        '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>'
        '<path d="M7 11V7a5 5 0 0 1 10 0v4"></path>'
    ),
    "plus": (
        '<line x1="12" y1="5" x2="12" y2="19"></line>'
        '<line x1="5" y1="12" x2="19" y2="12"></line>'
    ),
    "flag": (
        '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"></path>'
        '<line x1="4" y1="22" x2="4" y2="15"></line>'
    ),
    "mic": (
        '<path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>'
        '<path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>'
        '<line x1="12" y1="19" x2="12" y2="23"></line>'
        '<line x1="8" y1="23" x2="16" y2="23"></line>'
    ),
    "github": (
        '<path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 '
        '6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 '
        '2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 '
        '5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path>'
    ),
}


def icon(name: str, size: int = 20, color: str = "#58a6ff") -> str:
    """Retorna um ícone outline (estilo Lucide/Feather) como string SVG inline."""
    body = _ICON_PATHS.get(name, "")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round" '
        f'style="display:inline-block;vertical-align:middle;flex-shrink:0;">{body}</svg>'
    )


def heading(text: str, icon_name: str, level: int = 2, size: int = 22, color: str = "#58a6ff") -> None:
    """st.title/st.subheader com ícone SVG à esquerda, alinhado via flexbox."""
    tag = f"h{level}"
    st.markdown(
        f'<{tag} style="display:flex;align-items:center;gap:0.5rem;'
        f'margin:0.2rem 0 0.6rem 0;">{icon(icon_name, size, color)}'
        f'<span>{text}</span></{tag}>',
        unsafe_allow_html=True,
    )


def label(text: str, icon_name: str, size: int = 16, color: str = "#c9d1d9") -> None:
    """Rótulo inline em negrito com ícone, para substituir emojis fora de headings."""
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:0.4rem;'
        f'font-weight:600;margin:0.4rem 0;">{icon(icon_name, size, color)}'
        f'<span>{text}</span></div>',
        unsafe_allow_html=True,
    )


# ---------- Fundo animado "Matrix rain" (decorativo, sutil) ----------

_MATRIX_HTML = """
<canvas id="matrix-rain"></canvas>
<script>
(function () {
  var frame = window.frameElement;
  if (frame) {
    frame.style.cssText =
      "position:fixed;top:0;left:0;width:100vw;height:100vh;" +
      "z-index:-1;pointer-events:none;border:none;display:block;";
  }

  var canvas = document.getElementById("matrix-rain");
  var ctx = canvas.getContext("2d");
  canvas.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;opacity:0.5;";

  var fontSize = 14; // fonte pequena — evita o efeito "blocão"
  var drops = [];

  function resize() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    var columns = Math.max(1, Math.floor(canvas.width / fontSize));
    drops = new Array(columns).fill(0);
  }
  resize();
  window.addEventListener("resize", resize);

  var chars =
    "アイウエオカキクケコサシスセソタチツテト0123456789" +
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ$+-*/=%#&_(){}[]<>";

  var frameCount = 0;

  function draw() {
    requestAnimationFrame(draw);
    if (document.hidden) return;
    frameCount++;
    if (frameCount % 2 !== 0) return; // reduz taxa de renderização (CPU)

    // rastro: em vez de limpar o canvas, pinta um véu semi-transparente por
    // cima do frame anterior — é isso que cria o fade characteristic do efeito
    ctx.fillStyle = "rgba(14, 17, 23, 0.08)";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.font = fontSize + "px monospace";

    for (var i = 0; i < drops.length; i++) {
      // ~97% de chance de pular o frame nessa coluna: cria espaçamento
      // vertical entre as gotas em vez de uma coluna sólida de caracteres
      if (Math.random() > 0.03) continue;

      var text = chars.charAt(Math.floor(Math.random() * chars.length));
      ctx.fillStyle = "rgba(63, 185, 80, 0.55)"; // cabeça da gota, discreta
      ctx.fillText(text, i * fontSize, drops[i] * fontSize);

      drops[i]++;
      if (drops[i] * fontSize > canvas.height) {
        drops[i] = 0;
      }
    }
  }
  requestAnimationFrame(draw);
})();
</script>
"""


def render_matrix_background() -> None:
    """Injeta o canvas animado 'Matrix rain' como fundo fixo, atrás de todo o
    conteúdo do app. Precisa de components.v1.html (não st.markdown) porque
    <script> inserido via innerHTML/markdown não executa no navegador."""
    components.html(_MATRIX_HTML, height=0)
