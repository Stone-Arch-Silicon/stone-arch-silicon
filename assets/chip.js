/* ================================================================
   3D CHIP
   Three.js (r128, UMD build) is only fetched when the section gets close
   to the viewport, and the render loop sleeps while it is off screen.
   ================================================================ */
(function(){
  const canvas = document.getElementById('chip-canvas');
  const stage = document.getElementById('chipStage');
  if (!canvas || !stage) return;
  let started = false;

  const near = new IntersectionObserver(([e]) => {
    if (!e.isIntersecting || started) return;
    started = true; near.disconnect();
    const s = document.createElement('script');
    s.src = 'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js';
    s.async = true;
    s.onload = () => { try { initChip(); } catch(err){ console.warn('[SASi chip]', err); } };
    document.head.appendChild(s);
  }, { rootMargin: '600px 0px' });
  near.observe(stage);

  function initChip(){
    const Motion = window.SASi.Motion;
    const renderer = new THREE.WebGLRenderer({canvas, antialias:true, alpha:true});
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
    renderer.outputEncoding = THREE.sRGBEncoding;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 100);
    camera.position.set(0, 3.4, 7.2);
    camera.lookAt(0, -0.15, 0);

    const chip = new THREE.Group();
    scene.add(chip);

    // ---- package body ----
    const W = 2.3, D = 2.3, H = 0.36;
    const body = new THREE.Mesh(new THREE.BoxGeometry(W, H, D), new THREE.MeshStandardMaterial({color:0x0c0c0e, metalness:0.4, roughness:0.48}));
    chip.add(body);
    const rim = new THREE.Mesh(new THREE.BoxGeometry(W*1.03, H*0.5, D*1.03), new THREE.MeshStandardMaterial({color:0x070708, metalness:0.5, roughness:0.55}));
    rim.position.y = -H*0.28;
    chip.add(rim);

    // ---- lid: club logo. Loads async, so force a frame once it lands. ----
    const ttex = new THREE.TextureLoader().load('assets/logo.png', () => ensureLoop());
    ttex.encoding = THREE.sRGBEncoding;
    ttex.wrapS = ttex.wrapT = THREE.ClampToEdgeWrapping;
    ttex.repeat.set(1.4, 1.4);
    ttex.offset.set(-0.2, -0.2);
    // logo.png is non-power-of-two; mipmapped filtering renders NPOT textures black in WebGL1
    ttex.generateMipmaps = false;
    ttex.minFilter = THREE.LinearFilter;
    ttex.magFilter = THREE.LinearFilter;
    const top = new THREE.Mesh(new THREE.PlaneGeometry(W*0.995, D*0.995), new THREE.MeshStandardMaterial({
      map:ttex, emissive:0xffffff, emissiveMap:ttex, emissiveIntensity:0.14, metalness:0.25, roughness:0.6
    }));
    top.rotation.x = -Math.PI/2;
    top.position.y = H/2 + 0.002;
    chip.add(top);

    // ---- gold leads ----
    const pinMat = new THREE.MeshStandardMaterial({color:0xd9a93a, metalness:1.0, roughness:0.32});
    const L = 0.34, PW = 0.12, PT = 0.055, count = 9, yPin = -0.04;
    const reach = W/2 + L/2 - 0.03;
    const start = -0.84, end = 0.84, step = (end-start)/(count-1);
    const gx = new THREE.BoxGeometry(L, PT, PW), gz = new THREE.BoxGeometry(PW, PT, L);
    for (let i = 0; i < count; i++){
      const p = start + step*i;
      [[gx, reach, p], [gx, -reach, p], [gz, p, reach], [gz, p, -reach]].forEach(([g, x, z]) => {
        const m = new THREE.Mesh(g, pinMat); m.position.set(x, yPin, z); chip.add(m);
      });
    }

    // ---- soft contact shadow ----
    (function(){
      const S = 256, cv = document.createElement('canvas'); cv.width = cv.height = S;
      const c = cv.getContext('2d');
      const grd = c.createRadialGradient(S/2, S/2, 10, S/2, S/2, S/2);
      grd.addColorStop(0, 'rgba(0,0,0,.55)'); grd.addColorStop(1, 'rgba(0,0,0,0)');
      c.fillStyle = grd; c.fillRect(0, 0, S, S);
      const sh = new THREE.Mesh(new THREE.PlaneGeometry(3.8, 3.8), new THREE.MeshBasicMaterial({map:new THREE.CanvasTexture(cv), transparent:true, depthWrite:false}));
      sh.rotation.x = -Math.PI/2; sh.position.y = -0.95; chip.add(sh);
    })();

    // ---- lights: neutral key, warm fill to pick up the gold, cool rim ----
    scene.add(new THREE.AmbientLight(0x404044, 0.55));
    scene.add(new THREE.HemisphereLight(0xf2f0ea, 0x0b0b0c, 0.55));
    const key = new THREE.DirectionalLight(0xffffff, 1.15); key.position.set(4, 6, 4); scene.add(key);
    const warm = new THREE.PointLight(0xffd28a, 0.9, 30); warm.position.set(-3, 2, 4); scene.add(warm);
    const rimL = new THREE.DirectionalLight(0xbcc8d6, 0.7); rimL.position.set(-4, 3, -5); scene.add(rimL);

    // ---- interaction ----
    let rotY = 0.7, rotX = 0.1, velY = 0, velX = 0, dragging = false, px = 0, py = 0;
    let visible = true, looping = false, rafId = null;
    let probed = false, probeFrames = 0, probeLast = 0, probeSum = 0, slow = false;

    canvas.addEventListener('pointerdown', e => { dragging = true; px = e.clientX; py = e.clientY; canvas.setPointerCapture(e.pointerId); ensureLoop(); });
    addEventListener('pointermove', e => {
      if (!dragging) return;
      const dx = e.clientX - px, dy = e.clientY - py; px = e.clientX; py = e.clientY;
      rotY += dx*0.008; rotX += dy*0.006; velY = dx*0.008; velX = dy*0.006;
    });
    addEventListener('pointerup', () => { dragging = false; });

    function resize(){
      const w = stage.clientWidth, h = stage.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w/h; camera.updateProjectionMatrix();
      ensureLoop();
    }
    new ResizeObserver(resize).observe(stage);
    new IntersectionObserver(([e]) => { visible = e.isIntersecting; if (visible) ensureLoop(); }).observe(stage);
    resize();

    function tick(){
      looping = true;
      rafId = requestAnimationFrame(tick);
      if (document.hidden) return;
      const t = performance.now();
      const auto = Motion.on && !slow;
      if (!dragging){
        if (auto) rotY += 0.0018;
        rotY += velY; rotX += velX;
        velY *= 0.93; velX *= 0.93;
      }
      rotX = Math.max(-1.15, Math.min(0.25, rotX));
      chip.rotation.y = rotY; chip.rotation.x = rotX;
      chip.position.y = auto ? Math.sin(t*0.0008)*0.035 : 0;
      renderer.render(scene, camera);

      // one-time live performance probe: stop the idle spin on machines that struggle
      if (!probed && auto){
        if (probeFrames > 4) probeSum += t - probeLast;
        probeLast = t; probeFrames++;
        if (probeFrames >= 45){ probed = true; if (1000 / (probeSum / (probeFrames - 5)) < 40) slow = true; }
      }
      const settled = !dragging && Math.abs(velX) < 0.0001 && Math.abs(velY) < 0.0001;
      if ((!visible || !auto) && settled){ cancelAnimationFrame(rafId); rafId = null; looping = false; }
    }
    function ensureLoop(){ if (!looping) tick(); }
    Motion.subscribe(() => ensureLoop());
    ensureLoop();
  }
})();
