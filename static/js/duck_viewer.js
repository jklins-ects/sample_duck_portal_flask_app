import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { OBJLoader } from "three/addons/loaders/OBJLoader.js";
import { MTLLoader } from "three/addons/loaders/MTLLoader.js";

export class DuckViewer {
    constructor(containerEl, modelBaseUrl = "/static/models/") {
        this.containerEl = containerEl;
        this.modelBaseUrl = modelBaseUrl;

        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x111111);

        const w = this.containerEl.clientWidth;
        const h = this.containerEl.clientHeight;

        this.camera = new THREE.PerspectiveCamera(60, w / h, 0.01, 1000);
        this.camera.position.set(0, 1.4, 3);

        this.renderer = new THREE.WebGLRenderer({ antialias: true });
        this.renderer.setSize(w, h);
        this.renderer.setPixelRatio(window.devicePixelRatio);

        this.containerEl.appendChild(this.renderer.domElement);

        this.scene.add(new THREE.AmbientLight(0xffffff, 0.65));
        const sun = new THREE.DirectionalLight(0xffffff, 1.0);
        sun.position.set(5, 10, 5);
        this.scene.add(sun);

        this.controls = new OrbitControls(
            this.camera,
            this.renderer.domElement,
        );
        this.controls.enableDamping = true;

        this.duckGroup = new THREE.Group();
        this.scene.add(this.duckGroup);

        this._duckObject = null;
        this._animHandle = null;

        this._startRenderLoop();
        this._listenResize();
    }

    _listenResize() {
        const onResize = () => {
            const w = this.containerEl.clientWidth;
            const h = this.containerEl.clientHeight;
            this.camera.aspect = w / h;
            this.camera.updateProjectionMatrix();
            this.renderer.setSize(w, h);
        };

        window.addEventListener("resize", onResize);
        this._cleanupResize = () =>
            window.removeEventListener("resize", onResize);
    }

    _startRenderLoop() {
        const tick = () => {
            this.controls.update();
            this.renderer.render(this.scene, this.camera);
            this._animHandle = requestAnimationFrame(tick);
        };
        tick();
    }

    async loadModelOnce() {
        if (this._duckObject) return;

        const mtlLoader = new MTLLoader();
        mtlLoader.setPath(this.modelBaseUrl);

        const materials = await new Promise((resolve, reject) => {
            mtlLoader.load("duck.mtl", resolve, undefined, reject);
        });

        materials.preload();

        const objLoader = new OBJLoader();
        objLoader.setMaterials(materials);
        objLoader.setPath(this.modelBaseUrl);

        const obj = await new Promise((resolve, reject) => {
            objLoader.load("duck.obj", resolve, undefined, reject);
        });

        // Scale & center like your viewer
        const box1 = new THREE.Box3().setFromObject(obj);
        const size1 = new THREE.Vector3();
        box1.getSize(size1);

        const maxDim = Math.max(size1.x, size1.y, size1.z) || 1;
        const scale = 2 / maxDim;
        obj.scale.setScalar(scale);

        const box2 = new THREE.Box3().setFromObject(obj);
        const center = new THREE.Vector3();
        box2.getCenter(center);
        obj.position.sub(center);

        // Clone materials so per-portal recolors don’t bleed
        obj.traverse((child) => {
            if (!child.isMesh) return;
            if (Array.isArray(child.material)) {
                child.material = child.material.map((m) => m.clone());
            } else {
                child.material = child.material.clone();
            }
        });

        this._duckObject = obj;
        this.duckGroup.add(this._duckObject);
    }

    setDuckColors(duck) {
        if (!this._duckObject) return;

        const isDerpy = !!duck.derpy;

        // Map your DB body -> mesh names you used in the viewer.
        // Adjust these keys once you know your exact mesh/material names.
        const duck_colors = {
            head: duck.body?.head ?? "yellow",
            front_left: duck.body?.front1 ?? "yellow",
            front_right: duck.body?.front2 ?? "yellow",
            rear_left: duck.body?.back1 ?? "yellow",
            rear_right: duck.body?.back2 ?? "yellow",

            // eyes logic from your viewer concept
            eyes: isDerpy ? "white" : "black",
            normal_pupil: "white",
            derpy_eyes: "black",

            // fallback
            beak: "orange",
        };

        this._duckObject.traverse((child) => {
            if (!child.isMesh) return;

            // Some models use mesh name for coloring, others use material name.
            // We’ll try both and fall back to yellow.
            const meshKey = child.name;
            const mat = child.material;

            const setColor = (m, key) => {
                if (!m || !m.color) return;
                const chosen =
                    duck_colors[key] ?? duck_colors[m.name] ?? "yellow";
                m.color.set(chosen);
            };

            if (Array.isArray(mat)) {
                for (const m of mat) {
                    console.log(m);
                    let key = m.name;
                    setColor(m, key);
                }
            } else {
                setColor(mat, meshKey);
            }
        });
    }

    async showDuck(duck) {
        await this.loadModelOnce();
        this._duckObject.visible = true;
        this.setDuckColors(duck);
    }

    clearDuck() {
        if (this._duckObject) this._duckObject.visible = false;
    }

    destroy() {
        if (this._animHandle) cancelAnimationFrame(this._animHandle);
        if (this._cleanupResize) this._cleanupResize();
        this.renderer.dispose();
        this.containerEl.innerHTML = "";
    }
}
