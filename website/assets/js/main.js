(() => {
  const root = document.documentElement;
  const fx = document.getElementById("fx");
  const navToggle = document.querySelector(".nav-toggle");
  const mobileNav = document.querySelector(".mobile-nav");
  const themeButtons = [...document.querySelectorAll(".theme-btn")];
  const downloadBtn = document.getElementById("download-btn");
  const downloadStatus = document.getElementById("download-status");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  const THEMES = {
    grass_block: { orb: [85, 255, 85], dust: [255, 246, 200], fly: [212, 255, 74] },
    the_end: { orb: [200, 100, 255], dust: [210, 180, 255], fly: [255, 80, 255] },
    nether: { orb: [255, 160, 50], dust: [255, 200, 140], fly: [255, 100, 20] },
    ocean: { orb: [80, 200, 255], dust: [180, 220, 255], fly: [50, 255, 200] },
    twilight: { orb: [100, 255, 150], dust: [200, 255, 220], fly: [255, 220, 80] },
    cherry: { orb: [255, 150, 200], dust: [255, 230, 240], fly: [255, 180, 220] },
    mushroom: { orb: [242, 240, 250], dust: [232, 226, 238], fly: [255, 132, 148] },
    snowy: { orb: [255, 255, 255], dust: [226, 242, 255], fly: [140, 220, 255] },
    desert: { orb: [255, 236, 170], dust: [255, 245, 210], fly: [255, 200, 60] },
    deep_dark: { orb: [42, 182, 172], dust: [124, 222, 212], fly: [0, 255, 212] },
    badlands: { orb: [255, 170, 90], dust: [255, 200, 150], fly: [255, 220, 120] },
    lush_caves: { orb: [150, 230, 120], dust: [200, 245, 180], fly: [170, 255, 120] },
    amethyst: { orb: [202, 162, 255], dust: [230, 210, 255], fly: [170, 120, 255] },
    mangrove: { orb: [255, 170, 110], dust: [230, 200, 170], fly: [255, 230, 120] },
  };

  let currentTheme = "grass_block";
  let particles = [];
  let raf = 0;
  let ctx = null;

  function setTheme(key) {
    currentTheme = THEMES[key] ? key : "grass_block";
    root.dataset.theme = currentTheme;
    themeButtons.forEach((btn) => {
      const on = btn.dataset.theme === currentTheme;
      btn.setAttribute("aria-pressed", String(on));
      const state = btn.querySelector(".theme-state");
      if (state) state.textContent = on ? "当前主题" : "点击切换";
    });
    spawnParticles();
  }

  function spawnParticles() {
    if (!ctx || reduceMotion.matches) return;
    const palette = THEMES[currentTheme];
    const w = fx.width;
    const h = fx.height;
    particles = Array.from({ length: 48 }, (_, i) => {
      const kind = i % 3;
      const color = kind === 0 ? palette.orb : kind === 1 ? palette.dust : palette.fly;
      return {
        x: Math.random() * w,
        y: Math.random() * h,
        r: kind === 1 ? 1.2 : 2 + Math.random() * 2,
        vx: (Math.random() - 0.5) * 0.4,
        vy: kind === 0 ? -0.25 - Math.random() * 0.35 : (Math.random() - 0.5) * 0.3,
        a: 0.35 + Math.random() * 0.5,
        color,
      };
    });
  }

  function resizeFx() {
    if (!fx) return;
    fx.width = window.innerWidth;
    fx.height = window.innerHeight;
    spawnParticles();
  }

  function tick() {
    if (!ctx || reduceMotion.matches) return;
    ctx.clearRect(0, 0, fx.width, fx.height);
    particles.forEach((p) => {
      p.x += p.vx;
      p.y += p.vy;
      if (p.y < -8) p.y = fx.height + 8;
      if (p.y > fx.height + 8) p.y = -8;
      if (p.x < -8) p.x = fx.width + 8;
      if (p.x > fx.width + 8) p.x = -8;
      ctx.fillStyle = `rgba(${p.color[0]},${p.color[1]},${p.color[2]},${p.a})`;
      ctx.fillRect(Math.floor(p.x), Math.floor(p.y), p.r * 2, p.r * 2);
    });
    raf = requestAnimationFrame(tick);
  }

  function setupFx() {
    if (!fx) return;
    ctx = fx.getContext("2d");
    resizeFx();
    window.addEventListener("resize", resizeFx, { passive: true });
    if (!reduceMotion.matches) tick();
  }

  function setupNav() {
    if (!navToggle || !mobileNav) return;
    navToggle.addEventListener("click", () => {
      const open = mobileNav.classList.toggle("is-open");
      navToggle.setAttribute("aria-expanded", String(open));
    });
    mobileNav.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        mobileNav.classList.remove("is-open");
        navToggle.setAttribute("aria-expanded", "false");
      });
    });
  }

  function setupThemes() {
    themeButtons.forEach((btn) => {
      btn.addEventListener("click", () => setTheme(btn.dataset.theme));
    });
    setTheme("grass_block");
  }

  function setupDownload() {
    if (!downloadBtn || !downloadStatus) return;

    function startDownload() {
      const href = downloadBtn.getAttribute("href");
      const link = document.createElement("a");
      link.href = href;
      link.setAttribute("download", "CBL_Launcher.exe");
      document.body.appendChild(link);
      link.click();
      link.remove();
      downloadStatus.hidden = true;
    }

    function showMissing() {
      downloadStatus.hidden = false;
      downloadStatus.innerHTML =
        '发布包尚未放进 <code>website/downloads/</code>，直链 CBL_Launcher.exe 不存在。' +
        '请按 <a href="./downloads/README.txt">website/downloads/README.txt</a> 的说明，' +
        '把构建产物复制到该目录，或运行 <code>python tools/build_release.py</code> 自动构建并投放。';
    }

    downloadBtn.addEventListener("click", async (event) => {
      event.preventDefault();
      const href = downloadBtn.getAttribute("href");
      if (window.location.protocol === "file:") {
        // file:// 下浏览器不允许 fetch 探测，无法 HEAD；直接交给浏览器下载。
        startDownload();
        return;
      }
      try {
        const res = await fetch(href, { method: "HEAD", cache: "no-store" });
        if (!res.ok) throw new Error("missing");
      } catch {
        showMissing();
        return;
      }
      startDownload();
    });
  }

  function setupMotion() {
    const gsapLib = window.gsap;
    if (!gsapLib || !window.ScrollTrigger) return;
    gsapLib.registerPlugin(window.ScrollTrigger);

    const mm = gsapLib.matchMedia();
    mm.add(
      {
        motion: "(prefers-reduced-motion: no-preference)",
        reduce: "(prefers-reduced-motion: reduce)",
      },
      (context) => {
        if (context.conditions.reduce) return;
        const words = document.querySelectorAll("[data-split] .word");
        if (words.length) {
          gsapLib.from(words, {
            y: 16,
            rotateX: -20,
            duration: 0.55,
            stagger: 0.06,
            ease: "expo.out",
          });
        }
        document.querySelectorAll("[data-reveal]").forEach((section) => {
          gsapLib.from(section.children, {
            opacity: 0,
            y: 24,
            duration: 0.5,
            stagger: 0.08,
            ease: "power2.out",
            scrollTrigger: { trigger: section, start: "top 85%" },
          });
        });
      }
    );
  }

  setupFx();
  setupNav();
  setupThemes();
  setupDownload();
  setupMotion();
})();
