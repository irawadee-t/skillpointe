'use client';

/**
 * AuroraWater — ciridae.com's hero background, adapted: vast out-of-focus
 * ribbons of warm light drifting through near-black, seen as if underwater,
 * with the SKILLED glass orb refracting the scene.
 *
 * The ciridae look is a handful of huge, heavily-blurred luminous shapes
 * gliding slowly on dark blue-black. This version keeps that language and
 * adds two things: the palette leans into brand red (#9d2235) alongside the
 * amber, and the whole field behaves slightly like water — a gentle
 * refraction wobble everywhere, ripple rings from clicks and ambient drops,
 * and a soft warp around the cursor, all subtle.
 *
 * Single-pass and stateless (no feedback buffers) — every frame is complete,
 * so it degrades gracefully in hidden tabs and under reduced motion.
 *
 * Fills its nearest positioned parent (renders absolutely inset-0):
 *
 *   <div className="relative h-screen overflow-hidden">
 *     <AuroraWater />
 *     <div className="relative z-10">…hero copy…</div>
 *   </div>
 *
 * Pure WebGL1, zero dependencies.
 */

import { useEffect, useRef } from 'react';

export interface AuroraWaterProps {
  className?: string;
  /** Fade the scene in on mount (default true). False = scene starts fully open. */
  intro?: boolean;
  /** Fade length in seconds when intro is on (default 2.4). */
  introSeconds?: number;
  /** Drift speed 0–100 (default 45). */
  speed?: number;
  /** Film grain 0–0.3 (default 0.09). */
  grain?: number;
  /** How much the light leans brand-red vs amber, 0–1 (default 0.65). */
  redAmount?: number;
  /** Orb placement in aspect-corrected units (default: landing hero's x .44, y .12, r .74). */
  orb?: { x: number; y: number; r: number };
}

const MAX_RIPPLES = 8;

const VERT = 'attribute vec2 aP; void main(){ gl_Position = vec4(aP,0.,1.); }';

const FRAG = `
precision highp float;
uniform vec2  uRes;
uniform float uTime;      // drift time (speed-scaled)
uniform float uClock;     // real seconds (ripples, grain)
uniform float uIntro;
uniform float uGrain;
uniform float uRedAmount;
uniform vec2  uCam;       // pointer parallax
uniform vec2  uStir;      // pointer in scene coords
uniform float uStirAmt;
uniform vec2  uSpherePos;
uniform float uSphereR;
uniform vec4  uRipples[${MAX_RIPPLES}]; // xy=center, z=birth clock, w=strength

float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123); }

float noise(vec2 p){
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i),               hash(i + vec2(1., 0.)), u.x),
               mix(hash(i + vec2(0., 1.)), hash(i + vec2(1., 1.)), u.x), u.y);
}

float fbm(vec2 p){
    float v = 0.0, a = 0.5;
    mat2 m = mat2(1.6, 1.2, -1.2, 1.6);
    for(int i = 0; i < 4; i++){
        v += a * noise(p);
        p = m * p;
        a *= 0.5;
    }
    return v;
}

float random(in vec2 st){
    return fract(sin(dot(st.xy, vec2(12.9898, 78.233))) * 43758.5453123);
}

mat2 rot(float a){ return mat2(cos(a), -sin(a), sin(a), cos(a)); }

// One out-of-focus light ribbon: an elongated gaussian on noise-warped
// coordinates, so the edge melts organically instead of reading as an oval.
float ribbon(vec2 p, vec2 center, float angle, vec2 stretch, float seed){
    vec2 q = rot(angle) * (p - center);
    q /= stretch;
    float d2 = dot(q, q);
    d2 *= 0.72 + 0.56 * fbm(q * 1.4 + seed + uTime * 0.08);
    return exp(-d2 * 2.1);
}

// The full light field at a point — also sampled through the orb's glass.
vec3 lightField(vec2 p){
    // slight everywhere-wobble: the scene is viewed through a water surface
    vec2 w = p + 0.018 * vec2(
        fbm(p * 2.3 + uTime * 0.14) - 0.5,
        fbm(p * 2.3 + 11.7 - uTime * 0.11) - 0.5);

    float t = uTime;

    // palette — amber/apricot from ciridae, pulled toward SKILLED red
    vec3 amber   = vec3(0.720, 0.220, 0.240);   // ember red (was amber)
    vec3 apricot = vec3(0.870, 0.380, 0.360);   // light red highlight (was apricot)
    vec3 red     = vec3(0.616, 0.133, 0.208);   // #9d2235
    vec3 wine    = vec3(0.360, 0.080, 0.130);
    vec3 slate   = vec3(0.160, 0.200, 0.270);   // ciridae's cool counterweight

    vec3 warmA = mix(amber, red,  uRedAmount * 0.85);
    vec3 warmB = mix(apricot, red, uRedAmount * 0.45);
    vec3 deep  = mix(slate, wine, uRedAmount * 0.7);

    // deep water base — blue-black with the faintest warm lift
    vec3 col = vec3(0.016, 0.018, 0.032);

    // ribbons on slow independent orbits — big, bright, blown out at the core
    vec2 cA = vec2(-0.55 + 0.18 * sin(t * 0.21), 0.10 + 0.14 * sin(t * 0.157 + 1.7));
    float aA = 0.7 + 0.12 * sin(t * 0.10);
    col += warmA * 1.5 * ribbon(w, cA, aA, vec2(0.52, 0.20), 3.1);
    // hot cream core inside the main ribbon, like an out-of-focus highlight
    col += vec3(0.97, 0.90, 0.78) * 0.75 * ribbon(w, cA, aA, vec2(0.26, 0.10), 3.1);

    col += warmB * 1.0 * ribbon(w,
        vec2(-0.30 + 0.12 * sin(t * 0.171 + 4.2), -0.32 + 0.10 * sin(t * 0.13 + 0.6)),
        -0.55 + 0.10 * sin(t * 0.09 + 2.0), vec2(0.60, 0.24), 7.9);

    col += red * 0.85 * ribbon(w,
        vec2(0.62 + 0.16 * sin(t * 0.147 + 2.8), 0.30 + 0.12 * sin(t * 0.118 + 5.1)),
        2.3 + 0.14 * sin(t * 0.08 + 1.1), vec2(0.55, 0.22), 12.4);

    col += deep * 0.75 * ribbon(w,
        vec2(0.50 + 0.14 * sin(t * 0.132 + 0.9), -0.24 + 0.12 * sin(t * 0.104 + 3.3)),
        -1.9 + 0.10 * sin(t * 0.07 + 4.6), vec2(0.70, 0.32), 21.2);

    col += wine * 0.65 * ribbon(w,
        vec2(0.05 + 0.20 * sin(t * 0.09 + 5.9), 0.44 + 0.10 * sin(t * 0.126 + 2.2)),
        1.1 + 0.16 * sin(t * 0.11 + 0.3), vec2(0.75, 0.34), 33.7);

    return col;
}

void main(){
    float aspect = uRes.x / uRes.y;
    vec2 uv01 = gl_FragCoord.xy / uRes;
    vec2 vUvA = vec2((uv01.x - 0.5) * aspect, uv01.y - 0.5);

    vec2 p = vUvA + uCam * vec2(0.06, 0.035);

    // ---- the water layer: ripples + cursor gently warp the light ----
    vec2 disp = vec2(0.0);
    float glint = 0.0;
    for(int i = 0; i < ${MAX_RIPPLES}; i++){
        vec4 rp = uRipples[i];
        float age = uClock - rp.z;
        if(rp.w > 0.001 && age > 0.0){
            vec2 dv = p - rp.xy;
            float d = length(dv);
            float front = d - 0.30 * age;
            float ring = exp(-70.0 * front * front);
            float fade = exp(-1.5 * age) * rp.w;
            float wave = sin(24.0 * front) * ring * fade;
            disp += (dv / max(d, 1e-4)) * wave * 0.020;
            glint += wave;
        }
    }
    vec2 sd = p - uStir;
    float sdist = length(sd);
    float stir = exp(-7.0 * sdist * sdist) * uStirAmt;
    disp += (sd / max(sdist, 1e-4)) * stir * 0.030;

    vec3 col = lightField(p + disp);
    // light catches the ripple crests, faintly
    col += vec3(0.94, 0.90, 0.84) * clamp(glint, 0.0, 1.0) * 0.10;

    // ---- glass orb, refracting the light field (InteractiveOrb optics) ----
    vec2 c = uSpherePos + uCam * vec2(0.15, 0.085);
    vec2 q = vUvA - c;
    float r = length(q) / uSphereR;

    float coverage = 1.0 - smoothstep(0.997, 1.003, r);
    if(coverage > 0.0){
        float rr = min(r, 0.9999);
        float z = sqrt(1.0 - rr * rr);
        vec3 n = normalize(vec3(q, z * uSphereR * 1.6));
        vec3 I = normalize(vec3(q * 0.22, -1.0));

        vec3 refl = reflect(I, n);
        vec3 r0 = refract(I, n, 0.016);
        vec3 r1 = refract(I, n, 0.016 * 0.99);
        vec3 r2 = refract(I, n, 0.016 * 0.98);
        float fres = 0.016 + 2.442 * pow(1.0 + dot(I, n), 4.206);
        fres = clamp(fres, 0.0, 1.0);

        vec3 refracted;
        refracted.r = lightField(uSpherePos + vec2(-r0.x, r0.y) * 0.34 / (abs(r0.z) + 0.30)).r;
        refracted.g = lightField(uSpherePos + vec2(-r1.x, r1.y) * 0.34 / (abs(r1.z) + 0.30)).g;
        refracted.b = lightField(uSpherePos + vec2(-r2.x, r2.y) * 0.34 / (abs(r2.z) + 0.30)).b;
        vec3 reflected = lightField(uSpherePos + vec2(-refl.x, refl.y) * 0.34 / (abs(refl.z) + 0.30));

        vec4 lens = mix(vec4(refracted, 0.75), vec4(reflected, 1.0), fres);
        float glow = pow(clamp(0.8 - n.z, 0.0, 1.0), 8.0) * 0.20;
        lens.rgb += glow;

        float a = clamp(lens.a, 0.0, 1.0) * coverage * uIntro;
        col = col * (1.0 - a) + lens.rgb * a;
    }

    // vignette + intro + grain
    float vig = 1.0 - smoothstep(0.55, 1.3, length(vUvA));
    col *= 0.78 + 0.22 * vig;
    col *= uIntro;

    float g = random(gl_FragCoord.xy + fract(uClock * 43.7) * 289.0);
    col += (g - 0.5) * uGrain;

    gl_FragColor = vec4(col, 1.0);
}`;

export default function AuroraWater({
  className,
  intro = true,
  introSeconds = 2.4,
  speed = 45,
  grain = 0.09,
  redAmount = 0.9,
  orb = { x: 0.44, y: 0.12, r: 0.74 },
}: AuroraWaterProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const propsRef = useRef({ speed, grain, redAmount, orb });
  propsRef.current = { speed, grain, redAmount, orb };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext('webgl', { antialias: false });
    if (!gl) return;
    if (gl.isContextLost()) gl.getExtension('WEBGL_lose_context')?.restoreContext();

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const sh = (type: number, src: string) => {
      const s = gl.createShader(type)!;
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
        throw new Error(gl.getShaderInfoLog(s) || 'shader error');
      }
      return s;
    };
    // A shader failure should degrade to an empty canvas, not crash the page.
    let prog: WebGLProgram;
    try {
      prog = gl.createProgram()!;
      gl.attachShader(prog, sh(gl.VERTEX_SHADER, VERT));
      gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FRAG));
      gl.linkProgram(prog);
    } catch (err) {
      console.error('AuroraWater shader error:', err);
      return;
    }
    gl.useProgram(prog);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const aP = gl.getAttribLocation(prog, 'aP');
    gl.enableVertexAttribArray(aP);
    gl.vertexAttribPointer(aP, 2, gl.FLOAT, false, 0, 0);

    const U: Record<string, WebGLUniformLocation | null> = {};
    [
      'uRes', 'uTime', 'uClock', 'uIntro', 'uGrain', 'uRedAmount', 'uCam',
      'uStir', 'uStirAmt', 'uSpherePos', 'uSphereR',
    ].forEach((n) => (U[n] = gl.getUniformLocation(prog, n)));
    const uRipples = gl.getUniformLocation(prog, 'uRipples[0]');
    const rippleData = new Float32Array(MAX_RIPPLES * 4);
    let rippleSlot = 0;
    let clockNow = 0;

    const spawnRipple = (x: number, y: number, strength: number) => {
      const o = rippleSlot * 4;
      rippleData[o] = x;
      rippleData[o + 1] = y;
      rippleData[o + 2] = clockNow;
      rippleData[o + 3] = strength;
      rippleSlot = (rippleSlot + 1) % MAX_RIPPLES;
    };

    const mouse = { x: 0, y: 0 };
    const cam = { x: 0, y: 0 };
    const stirTarget = { x: 10, y: 10 };
    const stir = { x: 10, y: 10 };
    let stirAmt = 0;
    let lastSpawn = { x: 10, y: 10, at: 0 };
    let nextDrop = 2.5;

    const toScene = (e: { clientX: number; clientY: number }) => {
      const rect = canvas.getBoundingClientRect();
      if (!rect.width || !rect.height) return null;
      const ux = (e.clientX - rect.left) / rect.width;
      const uy = (e.clientY - rect.top) / rect.height;
      if (ux < 0 || ux > 1 || uy < 0 || uy > 1) return null;
      const aspect = rect.width / rect.height;
      return { x: (ux - 0.5) * aspect, y: 0.5 - uy };
    };

    const onMove = (e: PointerEvent) => {
      mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
      mouse.y = -((e.clientY / window.innerHeight) * 2 - 1);
      const s = toScene(e);
      if (!s) return;
      if (stirAmt === 0) {
        stir.x = s.x;
        stir.y = s.y;
      }
      stirTarget.x = s.x;
      stirTarget.y = s.y;
      stirAmt = Math.min(stirAmt + 0.2, 1);
      const dx = s.x - lastSpawn.x;
      const dy = s.y - lastSpawn.y;
      if (!reduced && dx * dx + dy * dy > 0.03 && clockNow - lastSpawn.at > 0.25) {
        spawnRipple(s.x, s.y, 0.30);
        lastSpawn = { x: s.x, y: s.y, at: clockNow };
      }
    };

    const onDown = (e: PointerEvent) => {
      const s = toScene(e);
      if (s) spawnRipple(s.x, s.y, 1.0);
    };

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerdown', onDown);

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = Math.round((canvas.clientWidth || window.innerWidth) * dpr);
      const h = Math.round((canvas.clientHeight || window.innerHeight) * dpr);
      if (!w || !h || (w === canvas.width && h === canvas.height)) return;
      canvas.width = w;
      canvas.height = h;
      gl.viewport(0, 0, w, h);
      gl.uniform2f(U.uRes, w, h);
    };
    window.addEventListener('resize', resize);
    resize();

    let raf = 0;
    let t0: number | null = null;
    let time = 0;
    let introT = 0;
    let last = performance.now();

    const frame = (now: number) => {
      resize();
      const dt = Math.min((now - last) / 1000, 0.05);
      last = now;
      if (t0 === null) t0 = now;
      const s = (now - t0) / 1000;
      clockNow = s;

      // Intro runs on accumulated *rendered* time, not wall clock — a page
      // loaded in a background tab still plays its reveal when first seen.
      let progress = 1;
      if (intro && !reduced) {
        introT += dt;
        const t = Math.min(Math.max(introT / introSeconds, 0), 1);
        progress = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      }

      // ambient raindrops keep the surface alive when idle
      if (!reduced && s > nextDrop) {
        const aspect = (canvas.clientWidth || 1) / (canvas.clientHeight || 1);
        spawnRipple((Math.random() - 0.5) * aspect, Math.random() - 0.5, 0.25 + Math.random() * 0.25);
        nextDrop = s + 3.5 + Math.random() * 3.0;
      }

      const p = propsRef.current;
      const motion = reduced ? 0.15 : 1;
      time += dt * (p.speed / 100) * motion;
      cam.x += (mouse.x - cam.x) * 0.06;
      cam.y += (mouse.y - cam.y) * 0.06;
      stir.x += (stirTarget.x - stir.x) * 0.10;
      stir.y += (stirTarget.y - stir.y) * 0.10;
      stirAmt *= 0.96;

      gl.uniform1f(U.uTime, time);
      gl.uniform1f(U.uClock, s);
      gl.uniform1f(U.uIntro, progress);
      gl.uniform1f(U.uGrain, p.grain);
      gl.uniform1f(U.uRedAmount, p.redAmount);
      gl.uniform2f(U.uCam, -cam.x * 0.6, -cam.y * 0.3);
      gl.uniform2f(U.uStir, stir.x, stir.y);
      gl.uniform1f(U.uStirAmt, reduced ? 0 : stirAmt);
      gl.uniform2f(U.uSpherePos, p.orb.x, p.orb.y);
      gl.uniform1f(U.uSphereR, p.orb.r);
      gl.uniform4fv(uRipples, rippleData);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerdown', onDown);
      window.removeEventListener('resize', resize);
      // Deliberately NOT losing the WebGL context here: Strict Mode remounts
      // reuse the same canvas, and a lost context comes back dead. The browser
      // reclaims it with the canvas element.
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intro, introSeconds]);

  return (
    <canvas
      ref={canvasRef}
      className={className ?? 'absolute inset-0'}
      // Inline size guard: a canvas is a replaced element, so `inset-0` alone
      // does NOT stretch it — and without a CSS size, the buffer resize loop
      // feeds back on itself and the canvas grows without bound.
      style={{ width: '100%', height: '100%', display: 'block' }}
      aria-label="Vast out-of-focus ribbons of amber and crimson light drifting through dark water, refracted by a glass sphere; ripples spread where the cursor touches."
    />
  );
}
