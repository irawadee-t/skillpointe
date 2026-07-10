'use client';

/**
 * InteractiveOrb — the monopo.vn-style silk + glass-orb hero graphic.
 *
 * Fills its nearest positioned parent (renders absolutely inset-0), so drop it
 * in place of a hero <video>:
 *
 *   <div className="relative h-screen overflow-hidden">
 *     <InteractiveOrb />
 *     <div className="relative z-10">…hero copy…</div>
 *   </div>
 *
 * Pure WebGL1, zero dependencies. Mouse-parallax like monopo's site: the
 * fabric and the orb glide with the cursor at different rates. Colors are
 * SKILLED Nation sage/amber with brand red (#9d2235) sweeping through in
 * patches — dial with `redAmount`.
 */

import { useEffect, useRef } from 'react';

export interface InteractiveOrbProps {
  className?: string;
  /** Play the blob→bloom reveal on mount (default true). False = scene starts fully open. */
  intro?: boolean;
  /** Bloom length in seconds when intro is on (default 2.8). */
  introSeconds?: number;
  /** Flow speed 0–100 (default 45). */
  speed?: number;
  /** Film grain 0–0.3 (default 0.09). */
  grain?: number;
  /** How much brand red sweeps through the fabric, 0–1 (default 0.65). */
  redAmount?: number;
  /** Stripe density (default 0.26). */
  zoom?: number;
  /** Orb placement in aspect-corrected units (default monopo's: x .44, y .12, r .74). */
  orb?: { x: number; y: number; r: number };
}

const VERT = 'attribute vec2 aP; void main(){ gl_Position = vec4(aP,0.,1.); }';

const FRAG = `
precision highp float;
uniform vec2  uRes;
uniform float uTime;
uniform float uBgProgress;
uniform float uOpacityBackground;
uniform float uZoom;
uniform vec3  uBaseFirstColor;
uniform vec3  uBaseSecondColor;
uniform vec3  uRedColor;
uniform float uRedAmount;
uniform vec3  uAccentColor;
uniform float uAccentOpacity;
uniform float uBaseFrequency;
uniform float uGrain;
uniform vec2  uCam;
uniform vec2  uSpherePos;
uniform float uSphereR;
uniform float uEta;
uniform float uFresnelBias;
uniform float uFresnelScale;
uniform float uFresnelPower;
uniform float uSphereAlpha;
uniform float uRefractionPower;

vec4 permute(vec4 x){return mod(((x*34.0)+1.0)*x, 289.0);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159 - 0.85373472095314 * r;}
vec4 mod289v(vec4 x){return x - floor(x * (1.0 / 289.0)) * 289.0;}
vec4 perm(vec4 x){return mod289v(((x * 34.0) + 1.0) * x);}

float random(in vec2 st){
    return fract(sin(dot(st.xy, vec2(12.9898,78.233))) * 43758.5453123);
}

float noise(vec3 p){
    vec3 a = floor(p);
    vec3 d = p - a;
    d = d * d * (3.0 - 2.0 * d);
    vec4 b = a.xxyy + vec4(0.0, 1.0, 0.0, 1.0);
    vec4 k1 = perm(b.xyxy);
    vec4 k2 = perm(k1.xyxy + b.zzww);
    vec4 c = k2 + a.zzzz;
    vec4 k3 = perm(c);
    vec4 k4 = perm(c + 1.0);
    vec4 o1 = fract(k3 * (1.0 / 41.0));
    vec4 o2 = fract(k4 * (1.0 / 41.0));
    vec4 o3 = o2 * d.z + o1 * (1.0 - d.z);
    vec2 o4 = o3.yw * d.x + o3.xz * (1.0 - d.x);
    return o4.y * d.y + o4.x * (1.0 - d.y);
}

float snoise3(vec3 v){
  const vec2 C = vec2(1.0/6.0, 1.0/3.0);
  const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
  vec3 i  = floor(v + dot(v, C.yyy));
  vec3 x0 = v - i + dot(i, C.xxx);
  vec3 g = step(x0.yzx, x0.xyz);
  vec3 l = 1.0 - g;
  vec3 i1 = min(g.xyz, l.zxy);
  vec3 i2 = max(g.xyz, l.zxy);
  vec3 x1 = x0 - i1 + 1.0 * C.xxx;
  vec3 x2 = x0 - i2 + 2.0 * C.xxx;
  vec3 x3 = x0 - 1. + 3.0 * C.xxx;
  i = mod(i, 289.0);
  vec4 p = permute(permute(permute(
            i.z + vec4(0.0, i1.z, i2.z, 1.0))
          + i.y + vec4(0.0, i1.y, i2.y, 1.0))
          + i.x + vec4(0.0, i1.x, i2.x, 1.0));
  float n_ = 1.0/7.0;
  vec3 ns = n_ * D.wyz - D.xzx;
  vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
  vec4 x_ = floor(j * ns.z);
  vec4 y_ = floor(j - 7.0 * x_);
  vec4 x = x_ * ns.x + ns.yyyy;
  vec4 y = y_ * ns.x + ns.yyyy;
  vec4 h = 1.0 - abs(x) - abs(y);
  vec4 b0 = vec4(x.xy, y.xy);
  vec4 b1 = vec4(x.zw, y.zw);
  vec4 s0 = floor(b0)*2.0 + 1.0;
  vec4 s1 = floor(b1)*2.0 + 1.0;
  vec4 sh = -step(h, vec4(0.0));
  vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy;
  vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww;
  vec3 p0 = vec3(a0.xy, h.x);
  vec3 p1 = vec3(a0.zw, h.y);
  vec3 p2 = vec3(a1.xy, h.z);
  vec3 p3 = vec3(a1.zw, h.w);
  vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2,p2), dot(p3,p3)));
  p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
  vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
  m = m * m;
  return 42.0 * dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
}

mat2 rotate2d(float angle){
    return mat2(cos(angle),-sin(angle),
                sin(angle),cos(angle));
}

float lines(in vec2 pos, float b){
    float scale = 10.0;
    pos *= scale;
    return smoothstep(0.0, .5+b*.5, abs((sin(pos.x*3.1415)+b*2.0))*.5);
}

float circle(in vec2 _st, in float _radius, in float blurriness){
    vec2 dist = _st;
    return 1. - smoothstep(_radius-(_radius*blurriness), _radius+(_radius*blurriness), dot(dist,dist)*4.0);
}

vec3 bgColor(vec2 pA){
    vec3 dir = normalize(vec3(pA, 0.55));
    vec3 uv = dir * 1.55;
    float baseNoise = noise(uBaseFrequency * uv + uTime);
    vec2 basePos = rotate2d(baseNoise) * uv.xy * uZoom;
    float basePattern = lines(basePos, .5);
    vec2 accentPos = rotate2d(baseNoise) * uv.xy * uZoom;
    float accentPattern = lines(accentPos, .1);
    float redPatch = smoothstep(.42, .72, noise(uv * 1.15 + 7.31 + uTime * .35));
    vec3 warm = mix(uBaseSecondColor, uRedColor, redPatch * uRedAmount);
    vec3 baseMix = mix(uBaseFirstColor, warm, basePattern);
    vec3 accentMix = mix(baseMix, uAccentColor, accentPattern - (1. - uAccentOpacity));
    return accentMix;
}

vec3 bgSoft(vec2 pA){
    vec3 c = bgColor(pA);
    c += bgColor(pA + vec2( 0.009, 0.006));
    c += bgColor(pA + vec2(-0.009,-0.006));
    c += bgColor(pA + vec2(-0.006, 0.009));
    c += bgColor(pA + vec2( 0.006,-0.009));
    return c * 0.2;
}

vec4 bgFull(vec2 pA){
    float progress = uBgProgress;
    vec3 accentMix = bgSoft(pA);
    vec2 st = gl_FragCoord.xy / uRes.xy - vec2(.5);
    st.y *= uRes.y / uRes.x;
    float c = circle(st, .09 + progress * 10.11, 2.);
    float offX = pA.x + sin(pA.y + uTime * 2.);
    float offY = pA.y - uTime * .2 - cos(uTime * 2.) * 0.1;
    float nc = (snoise3(vec3(offX, offY, uTime * 5.) * 2.)) * .03;
    float d = distance(uRes.xy*0.5, gl_FragCoord.xy) / uRes.y * (1.0-progress) * 2.3;
    float finalMask = smoothstep(.15, 1., pow(c, 6.) * 10. + nc * (1. - progress));
    vec4 finalImage = mix(vec4(0.0), vec4(accentMix, 1.0), clamp((finalMask + progress), 0., 1.)) * clamp(1.0 - d, 0., 1.);
    return vec4(finalImage.rgb, uOpacityBackground);
}

vec3 env(vec3 dir){
    vec2 p = uSpherePos + dir.xy * 0.34 / (abs(dir.z) + 0.30);
    return bgColor(p);
}

void main(){
    float aspect = uRes.x/uRes.y;
    vec2 uv01 = gl_FragCoord.xy/uRes;
    vec2 vUvA = vec2((uv01.x - 0.5) * aspect, uv01.y - 0.5);

    vec2 pA = vUvA + uCam * vec2(0.075, 0.045);
    vec4 bg = bgFull(pA);
    vec3 col = bg.rgb * bg.a;

    vec2 c = uSpherePos + uCam * vec2(0.15, 0.085);
    vec2 q = vUvA - c;
    float r = length(q) / uSphereR;

    float coverage = 1.0 - smoothstep(0.997, 1.003, r);
    if(coverage > 0.0){
        float rr = min(r, 0.9999);
        float z = sqrt(1.0 - rr*rr);
        vec3 n = normalize(vec3(q, z * uSphereR * 1.6));
        vec3 I = normalize(vec3(q * 0.22, -1.0));

        vec3 refl = reflect(I, n);
        vec3 r0 = refract(I, n, uEta);
        vec3 r1 = refract(I, n, uEta * 0.99);
        vec3 r2 = refract(I, n, uEta * 0.98);
        float fres = uFresnelBias + uFresnelScale * pow(1.0 + dot(I, n), uFresnelPower);
        fres = clamp(fres, 0.0, 1.0);

        vec3 refracted;
        refracted.r = env(vec3(-r0.x, r0.yz)).r;
        refracted.g = env(vec3(-r1.x, r1.yz)).g;
        refracted.b = env(vec3(-r2.x, r2.yz)).b;
        vec3 reflected = env(vec3(-refl.x, refl.yz));

        vec4 lens = mix(vec4(refracted, uRefractionPower),
                        vec4(reflected, 1.0) * uSphereAlpha,
                        fres);
        float glow = pow(clamp(0.8 - n.z, 0.0, 1.0), 8.0) * 0.18 * uSphereAlpha;
        lens.rgb += glow;

        float a = clamp(lens.a, 0.0, 1.0) * coverage * smoothstep(0.0, 0.22, uBgProgress);
        col = col * (1.0 - a) + lens.rgb * a;
    }

    float g = random(gl_FragCoord.xy + fract(uTime * 43.7) * 289.0);
    col += (g - .5) * uGrain;

    gl_FragColor = vec4(col, 1.0);
}`;

export default function InteractiveOrb({
  className,
  intro = true,
  introSeconds = 2.8,
  speed = 45,
  grain = 0.09,
  redAmount = 0.65,
  zoom = 0.26,
  orb = { x: 0.44, y: 0.12, r: 0.74 },
}: InteractiveOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const propsRef = useRef({ speed, grain, redAmount, zoom, orb });
  propsRef.current = { speed, grain, redAmount, zoom, orb };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext('webgl', { antialias: false });
    if (!gl) return;
    // React Strict Mode mounts → unmounts → remounts; a canvas keeps handing
    // back the same context, so revive it if a previous cleanup lost it.
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
    const prog = gl.createProgram()!;
    gl.attachShader(prog, sh(gl.VERTEX_SHADER, VERT));
    gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(prog);
    gl.useProgram(prog);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const aP = gl.getAttribLocation(prog, 'aP');
    gl.enableVertexAttribArray(aP);
    gl.vertexAttribPointer(aP, 2, gl.FLOAT, false, 0, 0);

    const U: Record<string, WebGLUniformLocation | null> = {};
    [
      'uRes', 'uTime', 'uBgProgress', 'uOpacityBackground', 'uZoom', 'uBaseFirstColor',
      'uBaseSecondColor', 'uRedColor', 'uRedAmount', 'uAccentColor', 'uAccentOpacity',
      'uBaseFrequency', 'uGrain', 'uCam', 'uSpherePos', 'uSphereR', 'uEta', 'uFresnelBias',
      'uFresnelScale', 'uFresnelPower', 'uSphereAlpha', 'uRefractionPower',
    ].forEach((n) => (U[n] = gl.getUniformLocation(prog, n)));

    // monopo's exact constants; palette = monopo sage + amber, SKILLED red
    gl.uniform3f(U.uBaseFirstColor, 120 / 255, 158 / 255, 113 / 255);
    gl.uniform3f(U.uBaseSecondColor, 224 / 255, 148 / 255, 66 / 255);
    gl.uniform3f(U.uRedColor, 157 / 255, 34 / 255, 53 / 255);
    gl.uniform3f(U.uAccentColor, 0, 0, 0);
    gl.uniform1f(U.uAccentOpacity, 1.0);
    gl.uniform1f(U.uBaseFrequency, 2.6);
    gl.uniform1f(U.uFresnelBias, 0.016);
    gl.uniform1f(U.uFresnelScale, 2.442);
    gl.uniform1f(U.uEta, 0.016);
    gl.uniform1f(U.uFresnelPower, 4.206);

    const mouse = { x: 0, y: 0 };
    const cam = { x: 0, y: 0 };

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

    const onMove = (e: PointerEvent) => {
      mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
      mouse.y = -((e.clientY / window.innerHeight) * 2 - 1);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('resize', resize);
    resize();

    let raf = 0;
    let t0: number | null = null;
    let time = 0;
    let last = performance.now();

    const frame = (now: number) => {
      resize();
      const dt = Math.min((now - last) / 1000, 0.05);
      last = now;
      if (t0 === null) t0 = now;
      const s = (now - t0) / 1000;

      // bloom: the mask edge grows on an S-curve (progress = S²)
      let progress = 1;
      if (intro && !reduced) {
        const t = Math.min(Math.max(s / introSeconds, 0), 1);
        const S = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
        progress = 0.005 + 0.995 * S * S;
      }

      const p = propsRef.current;
      const motion = reduced ? 0.15 : 1;
      time += dt * (p.speed / 100) * 0.3 * motion;
      cam.x += (mouse.x - cam.x) * 0.06;
      cam.y += (mouse.y - cam.y) * 0.06;

      gl.uniform1f(U.uTime, time);
      gl.uniform1f(U.uBgProgress, progress);
      gl.uniform1f(U.uOpacityBackground, 1.0);
      gl.uniform1f(U.uZoom, p.zoom * (0.5 + 0.5 * Math.min(progress * 4, 1)));
      gl.uniform1f(U.uGrain, p.grain);
      gl.uniform1f(U.uRedAmount, p.redAmount);
      gl.uniform2f(U.uCam, cam.x * 0.6 * -1, -cam.y * 0.3);
      gl.uniform2f(U.uSpherePos, p.orb.x, p.orb.y);
      gl.uniform1f(U.uSphereR, p.orb.r);
      gl.uniform1f(U.uSphereAlpha, Math.sqrt(progress));
      gl.uniform1f(U.uRefractionPower, 0.75 * Math.sqrt(progress));
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('pointermove', onMove);
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
      aria-label="Silk-like ribbons of amber, sage and crimson on black, with a vast glass sphere that glides with the cursor."
    />
  );
}
