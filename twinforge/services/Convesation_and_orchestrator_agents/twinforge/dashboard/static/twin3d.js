/* ═══════════════════════════════════════════════════════════════
   TWINFORGE — Agent 4: 3D Real-Time Twin Renderer
   Procedural Three.js factory • Data-driven • Multi-floor
   WebSocket sensor streaming • 5 View Modes
   ═══════════════════════════════════════════════════════════════ */

const TwinForge3D = (() => {
    "use strict";

    // ── CONSTANTS ─────────────────────────────────────────────
    const BG_COLOR = 0x141A24;  // slate-navy (not black)
    const CYAN = 0x00D4FF;
    const ORANGE = 0xFF6B35;
    const GREEN = 0x00FF9D;
    const RED = 0xFF3D5A;
    const WARN = 0xFFB300;
    const PURPLE = 0xA259FF;
    const FLOOR_EDGE = 0x00D4FF;
    const GRID_COLOR = 0x1a2a3a;
    const WARM_WHITE = 0xFFE8CC;
    const STEEL_GRAY = 0x2a3a4a;
    const DARK_STEEL = 0x1a2232;
    const API_SCENE = "/api/dashboard/scene3d";
    const _wsProto3d = location.protocol === "https:" ? "wss:" : "ws:";
    const WS_SENSOR = `${_wsProto3d}//${location.host}/ws/sensors`;
    let particleSystem = null;

    // ── STATE ─────────────────────────────────────────────────
    let renderer, scene, camera, controls, composer;
    let bloomPass, clock;
    let canvas = null;
    let animId = null;
    let running = false;
    let sceneData = null;
    let machineMap = {};      // twin_id → {mesh, group, label, statusLight}
    let floorGroups = [];     // THREE.Group per floor
    let buildingGroup = null;
    let currentMode = "exterior";
    let wsSensors = null;
    let hoveredMachine = null;
    let selectedMachine = null;
    let raycaster, mouse;
    let labelRenderer;
    let pipelineMaterials = [];
    let explosionProgress = 0;
    let exploding = false;

    // ═══════════════════════════════════════════════════════════
    // INITIALISATION
    // ═══════════════════════════════════════════════════════════

    function init(canvasEl) {
        if (renderer) return;  // already initialised
        canvas = canvasEl;

        // Check WebGL
        const testCanvas = document.createElement("canvas");
        const gl = testCanvas.getContext("webgl2") || testCanvas.getContext("webgl");
        if (!gl) {
            canvas.parentElement.innerHTML = `<div class="three-no-webgl">
                <div class="empty-icon">⬡</div>
                <h3>WebGL Not Available</h3>
                <p>Your browser or device does not support WebGL. Please use a modern browser.</p>
            </div>`;
            return;
        }

        const W = canvas.parentElement.clientWidth;
        const H = canvas.parentElement.clientHeight;

        // Renderer
        renderer = new THREE.WebGLRenderer({
            canvas: canvas,
            antialias: true,
            alpha: false,
            powerPreference: "high-performance",
        });
        renderer.setSize(W, H);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        renderer.setClearColor(BG_COLOR);
        renderer.shadowMap.enabled = true;
        renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.2;

        // Scene
        scene = new THREE.Scene();
        scene.fog = new THREE.FogExp2(BG_COLOR, 0.008);

        // Camera
        camera = new THREE.PerspectiveCamera(45, W / H, 0.5, 500);
        camera.position.set(35, 30, 35);

        // Controls
        controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.08;
        controls.minDistance = 8;
        controls.maxDistance = 120;
        controls.maxPolarAngle = Math.PI / 2.1;
        controls.target.set(0, 5, 0);

        // Clock
        clock = new THREE.Clock();

        // Raycaster
        raycaster = new THREE.Raycaster();
        mouse = new THREE.Vector2();

        // ── Lighting ──
        setupLighting();

        // ── Ground plane ──
        setupGround();

        // ── Post-processing (Bloom) ──
        setupPostProcessing(W, H);

        // ── Events ──
        window.addEventListener("resize", onResize);
        renderer.domElement.addEventListener("mousemove", onMouseMove);
        renderer.domElement.addEventListener("click", onMouseClick);

        running = true;
        animate();
    }

    function setupLighting() {
        // Ambient — warm industrial tone
        const ambient = new THREE.AmbientLight(0x1a2a4a, 0.5);
        scene.add(ambient);

        // Hemisphere — sky blue / ground warm
        const hemi = new THREE.HemisphereLight(0x1a2a4a, 0x141a24, 0.6);
        scene.add(hemi);

        // Main directional — moon-like key light
        const dir = new THREE.DirectionalLight(0xd0e0f0, 0.7);
        dir.position.set(35, 50, 25);
        dir.castShadow = true;
        dir.shadow.mapSize.set(2048, 2048);
        dir.shadow.camera.left = -60;
        dir.shadow.camera.right = 60;
        dir.shadow.camera.top = 60;
        dir.shadow.camera.bottom = -60;
        dir.shadow.bias = -0.001;
        scene.add(dir);

        // Volumetric cyan fill from below-left
        const fillCyan = new THREE.PointLight(CYAN, 0.5, 100);
        fillCyan.position.set(-20, 3, -15);
        scene.add(fillCyan);

        // Orange accent from above-right (sunset feel)
        const fillOrange = new THREE.PointLight(ORANGE, 0.25, 80);
        fillOrange.position.set(30, 30, 20);
        scene.add(fillOrange);

        // Purple accent from rear
        const fillPurple = new THREE.PointLight(PURPLE, 0.12, 60);
        fillPurple.position.set(-10, 15, -25);
        scene.add(fillPurple);

        // Industrial spotlights (ceiling-mounted)
        const spot1 = new THREE.SpotLight(WARM_WHITE, 0.6, 50, Math.PI / 6, 0.5, 1.5);
        spot1.position.set(0, 25, 0);
        spot1.target.position.set(0, 0, 0);
        spot1.castShadow = true;
        scene.add(spot1);
        scene.add(spot1.target);

        // Visible cone for spotlight
        const coneGeo = new THREE.ConeGeometry(6, 20, 16, 1, true);
        const coneMat = new THREE.MeshBasicMaterial({
            color: WARM_WHITE, transparent: true, opacity: 0.015,
            side: THREE.DoubleSide, depthWrite: false
        });
        const cone = new THREE.Mesh(coneGeo, coneMat);
        cone.position.set(0, 15, 0);
        scene.add(cone);
    }

    function setupGround() {
        // Dark concrete ground
        const gridGeo = new THREE.PlaneGeometry(300, 300, 1, 1);
        const gridMat = new THREE.MeshStandardMaterial({
            color: 0x0f1520, roughness: 0.92, metalness: 0.08,
        });
        const ground = new THREE.Mesh(gridGeo, gridMat);
        ground.rotation.x = -Math.PI / 2;
        ground.position.y = -0.05;
        ground.receiveShadow = true;
        scene.add(ground);

        // Fine grid overlay
        const grid = new THREE.GridHelper(300, 120, GRID_COLOR, GRID_COLOR);
        grid.position.y = 0.01;
        grid.material.transparent = true;
        grid.material.opacity = 0.2;
        scene.add(grid);

        // Coarse accent grid
        const grid2 = new THREE.GridHelper(300, 30, 0x1e3a5a, 0x1e3a5a);
        grid2.position.y = 0.015;
        grid2.material.transparent = true;
        grid2.material.opacity = 0.15;
        scene.add(grid2);

        // Glowing border strips (like reference images)
        const stripGeo = new THREE.PlaneGeometry(100, 0.08);
        const stripMat = new THREE.MeshBasicMaterial({ color: CYAN, transparent: true, opacity: 0.35 });
        for (let z = -30; z <= 30; z += 30) {
            const s = new THREE.Mesh(stripGeo, stripMat.clone());
            s.rotation.x = -Math.PI / 2;
            s.position.set(0, 0.02, z);
            scene.add(s);
        }

        // Circuit pattern traces
        const circuitGeo = new THREE.BufferGeometry();
        const pts = [];
        for (let i = 0; i < 50; i++) {
            const x1 = (Math.random() - 0.5) * 160;
            const z1 = (Math.random() - 0.5) * 160;
            const x2 = x1 + (Math.random() - 0.5) * 25;
            pts.push(x1, 0.02, z1, x2, 0.02, z1);
            pts.push(x2, 0.02, z1, x2, 0.02, z1 + (Math.random() - 0.5) * 18);
        }
        circuitGeo.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
        const circuitMat = new THREE.LineBasicMaterial({ color: 0x0e1e30, transparent: true, opacity: 0.4 });
        scene.add(new THREE.LineSegments(circuitGeo, circuitMat));

        // Ambient particles (floating dust / data motes)
        setupParticles();
    }

    function setupParticles() {
        const count = 500;
        const positions = new Float32Array(count * 3);
        const colors = new Float32Array(count * 3);
        const sizes = new Float32Array(count);

        const cyanColor = new THREE.Color(CYAN);
        const purpleColor = new THREE.Color(PURPLE);

        for (let i = 0; i < count; i++) {
            positions[i * 3] = (Math.random() - 0.5) * 120;
            positions[i * 3 + 1] = Math.random() * 30;
            positions[i * 3 + 2] = (Math.random() - 0.5) * 120;

            const c = Math.random() > 0.7 ? purpleColor : cyanColor;
            colors[i * 3] = c.r;
            colors[i * 3 + 1] = c.g;
            colors[i * 3 + 2] = c.b;

            sizes[i] = Math.random() * 0.15 + 0.03;
        }

        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
        geometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1));

        const material = new THREE.PointsMaterial({
            size: 0.12,
            vertexColors: true,
            transparent: true,
            opacity: 0.4,
            sizeAttenuation: true,
            depthWrite: false,
        });

        particleSystem = new THREE.Points(geometry, material);
        scene.add(particleSystem);
    }

    function setupPostProcessing(W, H) {
        // Simple bloom using UnrealBloomPass from Three.js examples
        const postFxReady = (
            typeof THREE !== "undefined" &&
            typeof THREE.EffectComposer !== "undefined" &&
            typeof THREE.RenderPass !== "undefined" &&
            typeof THREE.UnrealBloomPass !== "undefined" &&
            typeof THREE.ShaderPass !== "undefined"
        );

        if (!postFxReady) {
            // Fallback: no post-processing available — render direct
            composer = null;
            console.warn("TwinForge3D: postprocessing disabled (missing Three.js postprocessing dependencies)");
            return;
        }
        const renderPass = new THREE.RenderPass(scene, camera);
        bloomPass = new THREE.UnrealBloomPass(
            new THREE.Vector2(W, H), 0.8, 0.4, 0.85
        );
        bloomPass.threshold = 0.2;
        bloomPass.strength = 0.6;
        bloomPass.radius = 0.5;

        composer = new THREE.EffectComposer(renderer);
        composer.addPass(renderPass);
        composer.addPass(bloomPass);
    }


    // ═══════════════════════════════════════════════════════════
    // FACTORY BUILDER — procedural from API data
    // ═══════════════════════════════════════════════════════════

    async function loadScene() {
        try {
            const res = await fetch(API_SCENE);
            sceneData = await res.json();
        } catch (e) {
            console.warn("scene3d fetch failed:", e);
            return;
        }

        clearFactory();

        if (!sceneData.floors || sceneData.floors.length === 0) {
            showEmpty3D();
            return;
        }

        buildingGroup = new THREE.Group();
        buildingGroup.name = "factory";
        scene.add(buildingGroup);

        const bldg = sceneData.building;

        sceneData.floors.forEach((floor, fi) => {
            const floorGrp = new THREE.Group();
            floorGrp.name = `floor_${floor.floor}`;
            floorGrp.userData = { floorIndex: fi, floorId: floor.floor, baseY: floor.y_offset };
            floorGrp.position.y = floor.y_offset;

            // ── Floor plate (transparent glass) ──
            buildFloorPlate(floorGrp, bldg, floor);

            // ── Machines ──
            floor.machines.forEach((m) => {
                buildMachine(floorGrp, m, floor.y_offset);
            });

            // ── Energy pipelines ──
            floor.pipelines.forEach((p) => {
                buildPipeline(floorGrp, p);
            });

            floorGroups.push(floorGrp);
            buildingGroup.add(floorGrp);
        });

        // ── Building outer shell (very transparent) ──
        buildOuterShell(bldg);

        // Camera framing
        const box = new THREE.Box3().setFromObject(buildingGroup);
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());
        controls.target.copy(center);
        camera.position.set(
            center.x + size.x * 1.2,
            center.y + size.y * 1.0,
            center.z + size.z * 1.2
        );
        controls.update();

        // Connect sensor WS
        connectSensorWS();

        updateHUD();
    }

    function clearFactory() {
        if (buildingGroup) {
            scene.remove(buildingGroup);
            buildingGroup.traverse((obj) => {
                if (obj.geometry) obj.geometry.dispose();
                if (obj.material) {
                    if (Array.isArray(obj.material)) obj.material.forEach(m => m.dispose());
                    else obj.material.dispose();
                }
            });
        }
        buildingGroup = null;
        floorGroups = [];
        machineMap = {};
        pipelineMaterials = [];
    }

    function showEmpty3D() {
        const hudInfo = document.getElementById("hud-info");
        if (hudInfo) {
            hudInfo.innerHTML = `
                <div class="hud-empty">
                    <div class="hud-empty-icon">⬡</div>
                    <div>No digital twins created yet</div>
                    <div class="hud-empty-hint">Use the chat to create machines</div>
                </div>`;
            hudInfo.classList.add("show");
        }
    }


    // ═══════════════════════════════════════════════════════════
    // FLOOR PLATE
    // ═══════════════════════════════════════════════════════════

    function buildFloorPlate(group, bldg, floor) {
        const w = bldg.width;
        const d = bldg.depth;
        const h = 0.18;

        // Concrete floor plate
        const plateGeo = new THREE.BoxGeometry(w, h, d);
        const plateMat = new THREE.MeshPhysicalMaterial({
            color: 0x1a2232,
            transparent: true,
            opacity: 0.55,
            roughness: 0.3,
            metalness: 0.6,
            clearcoat: 0.8,
            clearcoatRoughness: 0.15,
            side: THREE.DoubleSide,
        });
        const plate = new THREE.Mesh(plateGeo, plateMat);
        plate.position.y = -h / 2;
        plate.receiveShadow = true;
        group.add(plate);

        // Neon edge wireframe
        const edgeGeo = new THREE.EdgesGeometry(plateGeo);
        const edgeMat = new THREE.LineBasicMaterial({ color: FLOOR_EDGE, transparent: true, opacity: 0.8 });
        const edges = new THREE.LineSegments(edgeGeo, edgeMat);
        edges.position.copy(plate.position);
        group.add(edges);

        // Orange border accent (top perimeter glow strip)
        const borderW = new THREE.Mesh(
            new THREE.BoxGeometry(w + 0.1, 0.03, 0.06),
            new THREE.MeshBasicMaterial({ color: ORANGE, transparent: true, opacity: 0.7 })
        );
        borderW.position.set(0, 0.02, -d / 2);
        group.add(borderW);
        const borderW2 = borderW.clone();
        borderW2.position.z = d / 2;
        group.add(borderW2);
        const borderD = new THREE.Mesh(
            new THREE.BoxGeometry(0.06, 0.03, d + 0.1),
            new THREE.MeshBasicMaterial({ color: ORANGE, transparent: true, opacity: 0.7 })
        );
        borderD.position.set(-w / 2, 0.02, 0);
        group.add(borderD);
        const borderD2 = borderD.clone();
        borderD2.position.x = w / 2;
        group.add(borderD2);

        // Safety markings (yellow hazard stripes on floor)
        const stripeCount = Math.floor(w / 4);
        for (let i = 0; i < stripeCount; i++) {
            const stripe = new THREE.Mesh(
                new THREE.PlaneGeometry(0.15, d * 0.6),
                new THREE.MeshBasicMaterial({ color: 0xFFB300, transparent: true, opacity: 0.08 })
            );
            stripe.rotation.x = -Math.PI / 2;
            stripe.position.set(-w / 2 + 2 + i * 4, 0.02, 0);
            group.add(stripe);
        }

        // Cable trays (overhead I-beams)
        const trayMat = new THREE.MeshPhysicalMaterial({ color: STEEL_GRAY, metalness: 0.9, roughness: 0.3 });
        for (let z = -d / 3; z <= d / 3; z += d / 3) {
            const tray = new THREE.Mesh(new THREE.BoxGeometry(w * 0.8, 0.06, 0.15), trayMat);
            tray.position.set(0, 3.5, z);
            group.add(tray);
            // Support brackets
            for (let x = -w / 3; x <= w / 3; x += w / 3) {
                const bracket = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.4, 0.06), trayMat);
                bracket.position.set(x, 3.3, z);
                group.add(bracket);
            }
        }

        // Floor label
        const labelSprite = makeTextSprite(
            `Floor ${floor.floor}  •  ${floor.machine_count} machines`,
            { fontsize: 28, color: "#00D4FF", bgColor: "rgba(20,26,36,0.8)" }
        );
        labelSprite.position.set(-w / 2 + 1.5, 0.8, -d / 2 + 0.5);
        labelSprite.scale.set(6, 1.5, 1);
        group.add(labelSprite);

        // Corner beacons (4 corners, pulsing cyan dots)
        const beaconGeo = new THREE.SphereGeometry(0.15, 10, 10);
        const beaconMat = new THREE.MeshBasicMaterial({ color: CYAN });
        const corners = [
            [-w / 2, 0.15, -d / 2], [w / 2, 0.15, -d / 2],
            [-w / 2, 0.15, d / 2], [w / 2, 0.15, d / 2],
        ];
        corners.forEach(([x, y, z]) => {
            const b = new THREE.Mesh(beaconGeo, beaconMat.clone());
            b.position.set(x, y, z);
            b.userData.beacon = true;
            group.add(b);
            // Beacon glow ring
            const ring = new THREE.Mesh(
                new THREE.RingGeometry(0.2, 0.35, 16),
                new THREE.MeshBasicMaterial({ color: CYAN, transparent: true, opacity: 0.15, side: THREE.DoubleSide })
            );
            ring.rotation.x = -Math.PI / 2;
            ring.position.set(x, 0.02, z);
            ring.userData.beacon = true;
            group.add(ring);
        });

        // Floor-mounted industrial lights (small point lights per floor)
        const floorLight = new THREE.PointLight(CYAN, 0.15, 15);
        floorLight.position.set(0, 2.5, 0);
        group.add(floorLight);
    }


    // ═══════════════════════════════════════════════════════════
    // MACHINE GEOMETRY — type-specific procedural
    // ═══════════════════════════════════════════════════════════

    function buildMachine(group, machineData, floorY) {
        const mg = new THREE.Group();
        mg.name = machineData.twin_id;
        mg.userData = { ...machineData, isMachine: true };

        const statusColor = getStatusColor(machineData.status);
        const emissiveColor = getEmissiveColor(machineData.status);

        const baseMat = new THREE.MeshPhysicalMaterial({
            color: 0x1A2A3A,
            metalness: 0.85,
            roughness: 0.25,
            clearcoat: 0.6,
            emissive: new THREE.Color(emissiveColor),
            emissiveIntensity: machineData.status === "critical" ? 0.6 : 0.15,
        });

        const accentMat = new THREE.MeshPhysicalMaterial({
            color: statusColor,
            metalness: 0.6,
            roughness: 0.3,
            emissive: new THREE.Color(emissiveColor),
            emissiveIntensity: 0.4,
            transparent: true,
            opacity: 0.85,
        });

        switch (machineData.asset_type) {
            case "CNC": buildCNC(mg, baseMat, accentMat); break;
            case "Robot": buildRobot(mg, baseMat, accentMat); break;
            case "Press": buildPress(mg, baseMat, accentMat); break;
            case "Conveyor": buildConveyor(mg, baseMat, accentMat); break;
            case "Lathe": buildLathe(mg, baseMat, accentMat); break;
            case "Mill": buildCNC(mg, baseMat, accentMat); break;
            default: buildGenericMachine(mg, baseMat, accentMat); break;
        }

        // Status LED sphere on top
        const ledGeo = new THREE.SphereGeometry(0.18, 12, 12);
        const ledMat = new THREE.MeshBasicMaterial({ color: statusColor });
        const led = new THREE.Mesh(ledGeo, ledMat);
        led.position.y = 2.6;
        led.userData.isLED = true;
        mg.add(led);

        // Machine ID label
        const label = makeTextSprite(machineData.twin_id, {
            fontsize: 22,
            color: "#CFD8E8",
            bgColor: "rgba(11,15,26,0.8)",
        });
        label.position.y = 3.2;
        label.scale.set(3.5, 0.9, 1);
        mg.add(label);

        // ── CREATIVE: Holographic data panel floating above machine ──
        const holoPanel = buildHoloPanel(machineData);
        holoPanel.position.set(1.8, 4.2, 0);
        holoPanel.userData.holoPanel = true;
        mg.add(holoPanel);

        // ── CREATIVE: Orbiting data ring ──
        const ringGeo = new THREE.TorusGeometry(1.6, 0.02, 8, 48);
        const ringMat = new THREE.MeshBasicMaterial({
            color: statusColor, transparent: true, opacity: 0.25,
        });
        const dataRing = new THREE.Mesh(ringGeo, ringMat);
        dataRing.rotation.x = Math.PI / 2;
        dataRing.position.y = 1.5;
        dataRing.userData.orbitRing = true;
        mg.add(dataRing);

        // Orbiting dot on ring
        const orbitDot = new THREE.Mesh(
            new THREE.SphereGeometry(0.08, 8, 8),
            new THREE.MeshBasicMaterial({ color: statusColor })
        );
        orbitDot.position.set(1.6, 1.5, 0);
        orbitDot.userData.orbitDot = true;
        orbitDot.userData.orbitRadius = 1.6;
        orbitDot.userData.orbitSpeed = 1.5 + Math.random() * 0.8;
        orbitDot.userData.orbitY = 1.5;
        mg.add(orbitDot);

        // ── CREATIVE: Vertical scan line ──
        const scanLine = new THREE.Mesh(
            new THREE.PlaneGeometry(2.2, 0.02),
            new THREE.MeshBasicMaterial({
                color: CYAN, transparent: true, opacity: 0.15,
                side: THREE.DoubleSide, depthWrite: false
            })
        );
        scanLine.userData.scanLine = true;
        scanLine.userData.scanSpeed = 0.8 + Math.random() * 0.4;
        scanLine.position.y = 0.5;
        mg.add(scanLine);

        // ── CREATIVE: Base holographic circle on floor ──
        const baseRing = new THREE.Mesh(
            new THREE.RingGeometry(1.2, 1.4, 32),
            new THREE.MeshBasicMaterial({
                color: statusColor, transparent: true, opacity: 0.12,
                side: THREE.DoubleSide, depthWrite: false
            })
        );
        baseRing.rotation.x = -Math.PI / 2;
        baseRing.position.y = 0.02;
        baseRing.userData.baseRing = true;
        mg.add(baseRing);

        // Inner base ring
        const innerRing = new THREE.Mesh(
            new THREE.RingGeometry(0.8, 0.85, 32),
            new THREE.MeshBasicMaterial({
                color: CYAN, transparent: true, opacity: 0.08,
                side: THREE.DoubleSide, depthWrite: false
            })
        );
        innerRing.rotation.x = -Math.PI / 2;
        innerRing.position.y = 0.02;
        innerRing.userData.baseRing = true;
        mg.add(innerRing);

        // Position on floor
        mg.position.set(machineData.world_x, 0.15, machineData.world_z);
        mg.castShadow = true;
        group.add(mg);

        // Register in map
        machineMap[machineData.twin_id] = {
            group: mg,
            led: led,
            ledMat: ledMat,
            baseMat: baseMat,
            accentMat: accentMat,
            data: machineData,
        };
    }

    // ── HOLOGRAPHIC DATA PANEL ──
    function buildHoloPanel(data) {
        const panel = new THREE.Group();

        // Panel background (semi-transparent)
        const bgGeo = new THREE.PlaneGeometry(2.2, 1.6);
        const bgMat = new THREE.MeshBasicMaterial({
            color: 0x0a1828, transparent: true, opacity: 0.6,
            side: THREE.DoubleSide, depthWrite: false
        });
        const bg = new THREE.Mesh(bgGeo, bgMat);
        panel.add(bg);

        // Border frame
        const borderGeo = new THREE.EdgesGeometry(bgGeo);
        const borderMat = new THREE.LineBasicMaterial({ color: CYAN, transparent: true, opacity: 0.5 });
        panel.add(new THREE.LineSegments(borderGeo, borderMat));

        // Accent top line
        const topLine = new THREE.Mesh(
            new THREE.PlaneGeometry(2.2, 0.02),
            new THREE.MeshBasicMaterial({ color: CYAN, transparent: true, opacity: 0.8, side: THREE.DoubleSide })
        );
        topLine.position.y = 0.8;
        panel.add(topLine);

        // Data lines (as text sprites)
        const oee = data.oee ?? data.kpis?.oee ?? 0;
        const energy = data.energy_kwh ?? data.kpis?.energy_consumption_kwh ?? 0;
        const statusLabel = (data.status || "ok").toUpperCase();

        const lineTexts = [
            { text: `OEE: ${oee}%`, y: 0.4, color: oee > 75 ? "#00ff9d" : oee > 50 ? "#ffb300" : "#ff3d7f" },
            { text: `Status: ${statusLabel}`, y: 0.05, color: "#00D4FF" },
            { text: `Energy: ${energy} kWh`, y: -0.3, color: "#a259ff" },
            { text: `${data.asset_type || "Machine"}`, y: -0.6, color: "#6a8398" },
        ];

        lineTexts.forEach(({ text, y, color }) => {
            const sprite = makeTextSprite(text, { fontsize: 16, color: color, bgColor: "transparent" });
            sprite.position.set(0, y, 0.01);
            sprite.scale.set(2.2, 0.5, 1);
            panel.add(sprite);
        });

        // Corner brackets (L-shapes)
        const bracketMat = new THREE.LineBasicMaterial({ color: ORANGE, transparent: true, opacity: 0.6 });
        const corners = [[-1.1, 0.8], [1.1, 0.8], [-1.1, -0.8], [1.1, -0.8]];
        corners.forEach(([cx, cy]) => {
            const dx = cx > 0 ? -0.2 : 0.2;
            const dy = cy > 0 ? -0.2 : 0.2;
            const pts = [
                new THREE.Vector3(cx, cy + dy, 0.01),
                new THREE.Vector3(cx, cy, 0.01),
                new THREE.Vector3(cx + dx, cy, 0.01),
            ];
            const geo = new THREE.BufferGeometry().setFromPoints(pts);
            panel.add(new THREE.Line(geo, bracketMat));
        });

        // Connection line from panel to machine
        const connPts = [new THREE.Vector3(0, -0.8, 0), new THREE.Vector3(-1.8, -3.4, 0)];
        const connGeo = new THREE.BufferGeometry().setFromPoints(connPts);
        const connMat = new THREE.LineDashedMaterial({
            color: CYAN, transparent: true, opacity: 0.3,
            dashSize: 0.15, gapSize: 0.1,
        });
        const connLine = new THREE.Line(connGeo, connMat);
        connLine.computeLineDistances();
        panel.add(connLine);

        return panel;
    }

    // ── CNC Machine ──
    function buildCNC(group, baseMat, accentMat) {
        // Base housing
        const base = new THREE.Mesh(
            new THREE.BoxGeometry(2.0, 1.4, 1.6),
            baseMat
        );
        base.position.y = 0.7;
        base.castShadow = true;
        group.add(base);

        // Spindle column
        const column = new THREE.Mesh(
            new THREE.BoxGeometry(0.5, 1.2, 0.5),
            baseMat
        );
        column.position.set(0, 1.8, 0);
        group.add(column);

        // Spindle head
        const spindle = new THREE.Mesh(
            new THREE.CylinderGeometry(0.3, 0.3, 0.8, 12),
            accentMat
        );
        spindle.position.set(0, 2.4, 0);
        spindle.userData.rotate = true; // animate rotation
        group.add(spindle);

        // Work table
        const table = new THREE.Mesh(
            new THREE.BoxGeometry(1.8, 0.08, 1.2),
            new THREE.MeshPhysicalMaterial({ color: 0x2A3A4A, metalness: 0.9, roughness: 0.2 })
        );
        table.position.set(0, 0.15, 0);
        group.add(table);

        // Control panel
        const panel = new THREE.Mesh(
            new THREE.BoxGeometry(0.15, 0.6, 0.4),
            accentMat
        );
        panel.position.set(1.05, 1.1, 0);
        group.add(panel);
    }

    // ── Robot Arm ──
    function buildRobot(group, baseMat, accentMat) {
        // Base
        const base = new THREE.Mesh(
            new THREE.CylinderGeometry(0.6, 0.7, 0.5, 16),
            baseMat
        );
        base.position.y = 0.25;
        base.castShadow = true;
        group.add(base);

        // Lower arm
        const arm1 = new THREE.Mesh(
            new THREE.BoxGeometry(0.3, 1.4, 0.3),
            baseMat
        );
        arm1.position.set(0, 1.2, 0);
        group.add(arm1);

        // Joint sphere
        const joint = new THREE.Mesh(
            new THREE.SphereGeometry(0.22, 12, 12),
            accentMat
        );
        joint.position.set(0, 1.9, 0);
        group.add(joint);

        // Upper arm
        const arm2 = new THREE.Mesh(
            new THREE.BoxGeometry(0.25, 1.0, 0.25),
            baseMat
        );
        arm2.position.set(0.3, 2.0, 0);
        arm2.rotation.z = -0.6;
        group.add(arm2);

        // End effector
        const effector = new THREE.Mesh(
            new THREE.SphereGeometry(0.15, 8, 8),
            accentMat
        );
        effector.position.set(0.7, 2.3, 0);
        group.add(effector);
    }

    // ── Press Machine ──
    function buildPress(group, baseMat, accentMat) {
        // Frame
        const frame = new THREE.Mesh(
            new THREE.BoxGeometry(1.8, 2.8, 1.4),
            baseMat
        );
        frame.position.y = 1.4;
        frame.castShadow = true;
        group.add(frame);

        // Piston
        const piston = new THREE.Mesh(
            new THREE.CylinderGeometry(0.35, 0.35, 1.2, 12),
            accentMat
        );
        piston.position.set(0, 1.6, 0);
        piston.userData.piston = true;
        group.add(piston);

        // Base plate
        const basePlate = new THREE.Mesh(
            new THREE.BoxGeometry(2.2, 0.2, 1.6),
            new THREE.MeshPhysicalMaterial({ color: 0x2A3A4A, metalness: 0.9, roughness: 0.2 })
        );
        basePlate.position.y = 0.1;
        group.add(basePlate);
    }

    // ── Conveyor ──
    function buildConveyor(group, baseMat, accentMat) {
        // Belt body
        const belt = new THREE.Mesh(
            new THREE.BoxGeometry(3.0, 0.3, 0.8),
            baseMat
        );
        belt.position.y = 0.8;
        belt.castShadow = true;
        group.add(belt);

        // Legs
        for (let x of [-1.2, 0, 1.2]) {
            const leg = new THREE.Mesh(
                new THREE.BoxGeometry(0.1, 0.65, 0.7),
                baseMat
            );
            leg.position.set(x, 0.32, 0);
            group.add(leg);
        }

        // Rollers
        for (let x = -1.2; x <= 1.2; x += 0.6) {
            const roller = new THREE.Mesh(
                new THREE.CylinderGeometry(0.12, 0.12, 0.9, 8),
                accentMat
            );
            roller.position.set(x, 0.95, 0);
            roller.rotation.x = Math.PI / 2;
            roller.userData.roller = true;
            group.add(roller);
        }
    }

    // ── Lathe ──
    function buildLathe(group, baseMat, accentMat) {
        // Bed
        const bed = new THREE.Mesh(
            new THREE.BoxGeometry(2.8, 0.6, 1.0),
            baseMat
        );
        bed.position.y = 0.5;
        bed.castShadow = true;
        group.add(bed);

        // Headstock
        const headstock = new THREE.Mesh(
            new THREE.BoxGeometry(0.8, 1.0, 1.0),
            baseMat
        );
        headstock.position.set(-0.9, 1.3, 0);
        group.add(headstock);

        // Chuck
        const chuck = new THREE.Mesh(
            new THREE.CylinderGeometry(0.4, 0.4, 0.3, 16),
            accentMat
        );
        chuck.position.set(-0.3, 1.3, 0);
        chuck.rotation.z = Math.PI / 2;
        chuck.userData.rotate = true;
        group.add(chuck);

        // Tailstock
        const tail = new THREE.Mesh(
            new THREE.CylinderGeometry(0.15, 0.2, 0.6, 8),
            baseMat
        );
        tail.position.set(1.1, 1.1, 0);
        group.add(tail);
    }

    // ── Generic Machine ──
    function buildGenericMachine(group, baseMat, accentMat) {
        const body = new THREE.Mesh(
            new THREE.BoxGeometry(1.6, 1.8, 1.2),
            baseMat
        );
        body.position.y = 0.9;
        body.castShadow = true;
        group.add(body);

        // Top accent
        const top = new THREE.Mesh(
            new THREE.BoxGeometry(1.0, 0.15, 0.8),
            accentMat
        );
        top.position.y = 1.85;
        group.add(top);

        // Control face
        const face = new THREE.Mesh(
            new THREE.PlaneGeometry(0.5, 0.3),
            new THREE.MeshBasicMaterial({ color: CYAN, transparent: true, opacity: 0.5 })
        );
        face.position.set(0.81, 1.2, 0);
        face.rotation.y = Math.PI / 2;
        group.add(face);
    }


    // ═══════════════════════════════════════════════════════════
    // ENERGY PIPELINES
    // ═══════════════════════════════════════════════════════════

    function buildPipeline(group, pipeData) {
        const from = new THREE.Vector3(pipeData.from_pos[0], 0.4, pipeData.from_pos[1]);
        const to = new THREE.Vector3(pipeData.to_pos[0], 0.4, pipeData.to_pos[1]);
        const mid = new THREE.Vector3().addVectors(from, to).multiplyScalar(0.5);
        mid.y += 0.3;

        const curve = new THREE.QuadraticBezierCurve3(from, mid, to);
        const tubeGeo = new THREE.TubeGeometry(curve, 20, 0.06, 6, false);

        // Animated pipeline material
        const pipeMat = new THREE.MeshBasicMaterial({
            color: CYAN,
            transparent: true,
            opacity: 0.5,
        });
        const tube = new THREE.Mesh(tubeGeo, pipeMat);
        group.add(tube);

        // Glow effect — slightly larger transparent tube
        const glowMat = new THREE.MeshBasicMaterial({
            color: CYAN,
            transparent: true,
            opacity: 0.12,
        });
        const glowGeo = new THREE.TubeGeometry(curve, 20, 0.15, 6, false);
        const glow = new THREE.Mesh(glowGeo, glowMat);
        group.add(glow);

        // Flowing particle dots along pipeline
        const dotCount = 4;
        for (let i = 0; i < dotCount; i++) {
            const dotGeo = new THREE.SphereGeometry(0.08, 6, 6);
            const dotMat = new THREE.MeshBasicMaterial({ color: CYAN });
            const dot = new THREE.Mesh(dotGeo, dotMat);
            dot.userData.pipelineCurve = curve;
            dot.userData.pipelineOffset = i / dotCount;
            dot.userData.pipelineDot = true;
            group.add(dot);
        }

        pipelineMaterials.push(pipeMat);
    }


    // ═══════════════════════════════════════════════════════════
    // BUILDING OUTER SHELL
    // ═══════════════════════════════════════════════════════════

    function buildOuterShell(bldg) {
        const w = bldg.width + 2;
        const d = bldg.depth + 2;
        const h = bldg.total_height + 2;

        // ── Glass walls ──
        const shellGeo = new THREE.BoxGeometry(w, h, d);
        const shellMat = new THREE.MeshPhysicalMaterial({
            color: 0x1a2a3a,
            transparent: true,
            opacity: 0.06,
            roughness: 0.02,
            metalness: 0.4,
            clearcoat: 1.0,
            clearcoatRoughness: 0.05,
            side: THREE.BackSide,
            depthWrite: false,
        });
        const shell = new THREE.Mesh(shellGeo, shellMat);
        shell.position.y = h / 2;
        shell.userData.isShell = true;
        buildingGroup.add(shell);

        // ── Cyan wireframe edges ──
        const edgeGeo = new THREE.EdgesGeometry(shellGeo);
        const edgeMat = new THREE.LineBasicMaterial({ color: CYAN, transparent: true, opacity: 0.3 });
        const edges = new THREE.LineSegments(edgeGeo, edgeMat);
        edges.position.copy(shell.position);
        edges.userData.isShellEdge = true;
        buildingGroup.add(edges);

        // ── Orange roof border accent ──
        const roofEdgeGeo = new THREE.EdgesGeometry(new THREE.BoxGeometry(w, 0.06, d));
        const roofEdgeMat = new THREE.LineBasicMaterial({ color: ORANGE, transparent: true, opacity: 0.6 });
        const roofEdge = new THREE.LineSegments(roofEdgeGeo, roofEdgeMat);
        roofEdge.position.y = h + 0.03;
        buildingGroup.add(roofEdge);

        // ── Roof trusses (triangular, structural) ──
        const trussMat = new THREE.MeshPhysicalMaterial({ color: STEEL_GRAY, metalness: 0.9, roughness: 0.3, transparent: true, opacity: 0.7 });
        const trussCount = Math.max(3, Math.floor(d / 5));
        for (let i = 0; i < trussCount; i++) {
            const z = -d / 2 + 1 + i * (d - 2) / (trussCount - 1);
            // Horizontal beam
            const beam = new THREE.Mesh(new THREE.BoxGeometry(w - 1, 0.12, 0.12), trussMat);
            beam.position.set(0, h - 0.5, z);
            buildingGroup.add(beam);
            // Diagonal braces
            for (let side = -1; side <= 1; side += 2) {
                const brace = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.06, w * 0.52), trussMat);
                brace.position.set(side * w * 0.22, h - 0.8, z);
                brace.rotation.y = side * 0.3;
                buildingGroup.add(brace);
            }
        }

        // ── Structural columns (4 corners + midpoints) ──
        const colMat = new THREE.MeshPhysicalMaterial({ color: 0x2a3a4a, metalness: 0.85, roughness: 0.25 });
        const columnPositions = [
            [-w / 2, d / 2], [w / 2, d / 2], [-w / 2, -d / 2], [w / 2, -d / 2],
            [0, d / 2], [0, -d / 2], [-w / 2, 0], [w / 2, 0],
        ];
        columnPositions.forEach(([x, z]) => {
            const col = new THREE.Mesh(new THREE.BoxGeometry(0.3, h, 0.3), colMat);
            col.position.set(x, h / 2, z);
            buildingGroup.add(col);
            // Base bracket
            const base = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.1, 0.5), colMat);
            base.position.set(x, 0.05, z);
            buildingGroup.add(base);
        });

        // ── Window frames (horizontal bars on walls) ──
        const winMat = new THREE.LineBasicMaterial({ color: CYAN, transparent: true, opacity: 0.12 });
        for (let y = 1.5; y < h - 1; y += 2) {
            // Front and back walls
            for (let zSide of [-d / 2, d / 2]) {
                const pts2 = [new THREE.Vector3(-w / 2, y, zSide), new THREE.Vector3(w / 2, y, zSide)];
                const lineGeo = new THREE.BufferGeometry().setFromPoints(pts2);
                buildingGroup.add(new THREE.Line(lineGeo, winMat));
            }
            // Left and right walls
            for (let xSide of [-w / 2, w / 2]) {
                const pts3 = [new THREE.Vector3(xSide, y, -d / 2), new THREE.Vector3(xSide, y, d / 2)];
                const lineGeo2 = new THREE.BufferGeometry().setFromPoints(pts3);
                buildingGroup.add(new THREE.Line(lineGeo2, winMat));
            }
        }

        // ── Ventilation ducts on roof ──
        const ventMat = new THREE.MeshPhysicalMaterial({ color: 0x3a4a5a, metalness: 0.8, roughness: 0.3 });
        for (let i = 0; i < 3; i++) {
            const vent = new THREE.Mesh(new THREE.CylinderGeometry(0.35, 0.35, 0.8, 8), ventMat);
            vent.position.set(-w / 4 + i * w / 4, h + 0.4, -d / 4);
            buildingGroup.add(vent);
            // Vent cap
            const cap = new THREE.Mesh(new THREE.ConeGeometry(0.45, 0.3, 8), ventMat);
            cap.position.set(-w / 4 + i * w / 4, h + 0.95, -d / 4);
            buildingGroup.add(cap);
        }

        // ── Rooftop antenna / sensor array ──
        const antMat = new THREE.MeshBasicMaterial({ color: CYAN });
        const antenna = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 2, 6), antMat);
        antenna.position.set(w / 3, h + 1, d / 3);
        buildingGroup.add(antenna);
        const antTop = new THREE.Mesh(new THREE.SphereGeometry(0.1, 8, 8), antMat);
        antTop.position.set(w / 3, h + 2.1, d / 3);
        antTop.userData.beacon = true;
        buildingGroup.add(antTop);

        // ── Safety barriers near entrance ──
        const barrierMat = new THREE.MeshBasicMaterial({ color: ORANGE, transparent: true, opacity: 0.5 });
        for (let i = 0; i < 4; i++) {
            const post = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 1, 6), barrierMat);
            post.position.set(-w / 2 + 2 + i * 1.5, 0.5, d / 2 + 0.8);
            buildingGroup.add(post);
        }
    }


    // ═══════════════════════════════════════════════════════════
    // VIEW MODES
    // ═══════════════════════════════════════════════════════════

    function setViewMode(mode) {
        currentMode = mode;
        // Reset all modes first
        resetModes();

        switch (mode) {
            case "exterior": modeExterior(); break;
            case "cutaway": modeCutaway(); break;
            case "exploded": modeExploded(); break;
            case "blueprint": modeBlueprint(); break;
            case "heatmap": modeHeatmap(); break;
        }

        // Update toolbar active state
        document.querySelectorAll(".view3d-btn").forEach(b => {
            b.classList.toggle("active", b.dataset.mode === mode);
        });
    }

    function resetModes() {
        exploding = false;
        explosionProgress = 0;

        if (!buildingGroup) return;

        // Reset floor positions
        floorGroups.forEach(fg => {
            const baseY = fg.userData.baseY || 0;
            fg.position.y = baseY;
        });

        // Reset materials to default
        Object.values(machineMap).forEach(({ group, baseMat, accentMat }) => {
            baseMat.wireframe = false;
            baseMat.opacity = 1;
            baseMat.transparent = false;
            accentMat.wireframe = false;
            accentMat.opacity = 0.85;
        });

        // Show shell
        buildingGroup.traverse(obj => {
            if (obj.userData.isShell) { obj.visible = true; obj.material.opacity = 0.08; }
            if (obj.userData.isShellEdge) obj.visible = true;
        });

        // Reset camera to perspective
        if (camera.isPerspectiveCamera) {
            camera.fov = 45;
            camera.updateProjectionMatrix();
        }
    }

    function modeExterior() {
        // Default mode — all visible, shell semi-transparent
    }

    function modeCutaway() {
        // Hide front walls by making shell more transparent + clip
        buildingGroup.traverse(obj => {
            if (obj.userData.isShell) {
                obj.material.opacity = 0.03;
                obj.material.clippingPlanes = [new THREE.Plane(new THREE.Vector3(0, 0, 1), 0)];
            }
        });
        renderer.localClippingEnabled = true;
    }

    function modeExploded() {
        exploding = true;
    }

    function modeBlueprint() {
        // Orthographic top-down, wireframe
        camera.fov = 20;
        camera.updateProjectionMatrix();

        const bldg = sceneData.building;
        const center = new THREE.Vector3(0, bldg.total_height / 2, 0);
        camera.position.set(0, bldg.total_height + 30, 0);
        controls.target.copy(center);

        Object.values(machineMap).forEach(({ baseMat, accentMat }) => {
            baseMat.wireframe = true;
            baseMat.transparent = true;
            baseMat.opacity = 0.6;
            accentMat.wireframe = true;
        });

        buildingGroup.traverse(obj => {
            if (obj.userData.isShell) obj.visible = false;
            if (obj.userData.isShellEdge) obj.visible = false;
        });
    }

    function modeHeatmap() {
        Object.values(machineMap).forEach(({ baseMat, data }) => {
            const energy = data.energy_kwh || 0;
            const t = Math.min(energy / 100, 1);
            const heatColor = new THREE.Color().setHSL(0.6 - t * 0.6, 1.0, 0.4 + t * 0.2);
            baseMat.color.copy(heatColor);
            baseMat.emissive.copy(heatColor);
            baseMat.emissiveIntensity = 0.3 + t * 0.4;
        });

        buildingGroup.traverse(obj => {
            if (obj.userData.isShell) {
                obj.material.opacity = 0.04;
            }
        });
    }


    // ═══════════════════════════════════════════════════════════
    // ANIMATION LOOP
    // ═══════════════════════════════════════════════════════════

    function animate() {
        if (!running) return;
        animId = requestAnimationFrame(animate);

        const t = clock.getElapsedTime();
        const dt = clock.getDelta();

        controls.update();

        // ── Animate particles (floating dust) ──
        if (particleSystem) {
            const positions = particleSystem.geometry.attributes.position.array;
            for (let i = 0; i < positions.length; i += 3) {
                positions[i + 1] += Math.sin(t * 0.5 + i) * 0.003;
                if (positions[i + 1] > 32) positions[i + 1] = 0;
                if (positions[i + 1] < 0) positions[i + 1] = 30;
            }
            particleSystem.geometry.attributes.position.needsUpdate = true;
            particleSystem.rotation.y = t * 0.01;
        }

        // ── Animate machines ──
        if (buildingGroup) {
            buildingGroup.traverse(obj => {
                // Spinning spindles/chucks
                if (obj.userData.rotate) {
                    obj.rotation.y += 0.05;
                }
                // Piston animation
                if (obj.userData.piston) {
                    obj.position.y = 1.6 + Math.sin(t * 2) * 0.3;
                }
                // Roller rotation
                if (obj.userData.roller) {
                    obj.rotation.x += 0.03;
                }
                // Pipeline flowing dots
                if (obj.userData.pipelineDot) {
                    const curve = obj.userData.pipelineCurve;
                    const offset = obj.userData.pipelineOffset;
                    const pos = ((t * 0.3 + offset) % 1);
                    const point = curve.getPointAt(pos);
                    obj.position.copy(point);
                }
                // Beacon pulsing
                if (obj.userData.beacon) {
                    obj.scale.setScalar(0.8 + Math.sin(t * 3) * 0.3);
                }
                // ── CREATIVE: Orbiting dot on ring ──
                if (obj.userData.orbitDot) {
                    const r = obj.userData.orbitRadius;
                    const spd = obj.userData.orbitSpeed;
                    const oy = obj.userData.orbitY;
                    obj.position.x = Math.cos(t * spd) * r;
                    obj.position.z = Math.sin(t * spd) * r;
                    obj.position.y = oy + Math.sin(t * 2) * 0.05;
                }
                // ── CREATIVE: Vertical scan line sweeping ──
                if (obj.userData.scanLine) {
                    const spd = obj.userData.scanSpeed;
                    obj.position.y = 0.1 + ((Math.sin(t * spd) + 1) / 2) * 2.5;
                    obj.material.opacity = 0.08 + Math.sin(t * spd * 2) * 0.05;
                }
                // ── CREATIVE: Holo panel billboard toward camera ──
                if (obj.userData.holoPanel) {
                    obj.lookAt(camera.position);
                    obj.position.y = 4.2 + Math.sin(t * 0.8) * 0.15;
                }
                // ── CREATIVE: Base ring pulsing ──
                if (obj.userData.baseRing) {
                    const pulse = 0.08 + Math.sin(t * 1.5) * 0.04;
                    obj.material.opacity = pulse;
                    obj.rotation.z = t * 0.2;
                }
                // ── CREATIVE: Orbit ring slow rotation ──
                if (obj.userData.orbitRing) {
                    obj.rotation.z = t * 0.3;
                }
            });

            // Status LED pulsing for critical machines
            Object.values(machineMap).forEach(({ led, data }) => {
                if (data.status === "critical") {
                    led.scale.setScalar(1 + Math.sin(t * 5) * 0.3);
                } else if (data.status === "warning") {
                    led.scale.setScalar(1 + Math.sin(t * 3) * 0.15);
                }
            });

            // Exploded mode animation
            if (exploding && explosionProgress < 1) {
                explosionProgress = Math.min(explosionProgress + 0.015, 1);
                const ease = easeOutCubic(explosionProgress);
                floorGroups.forEach((fg, i) => {
                    const baseY = fg.userData.baseY || 0;
                    fg.position.y = baseY + i * ease * 6;
                });
            }
        }

        // ── Render ──
        if (composer) {
            composer.render();
        } else {
            renderer.render(scene, camera);
        }
    }


    // ═══════════════════════════════════════════════════════════
    // REAL-TIME SENSOR UPDATES
    // ═══════════════════════════════════════════════════════════

    function connectSensorWS() {
        if (wsSensors) {
            try { wsSensors.close(); } catch { }
        }
        try {
            wsSensors = new WebSocket(WS_SENSOR);
            wsSensors.onmessage = (e) => {
                const msg = JSON.parse(e.data);
                if (msg.type === "sensor_update" && msg.twins) {
                    msg.twins.forEach(twinSensor => {
                        updateMachineSensors(twinSensor.twin_id, twinSensor.sensor_data, twinSensor.anomaly_count);
                    });
                }
            };
            wsSensors.onclose = () => {
                if (running) setTimeout(connectSensorWS, 5000);
            };
        } catch { }
    }

    function updateMachineSensors(twinId, sensorData, anomalyCount) {
        const entry = machineMap[twinId];
        if (!entry) return;

        // Update status based on anomaly count
        let newStatus = "ok";
        if (anomalyCount > 2) newStatus = "critical";
        else if (anomalyCount > 0) newStatus = "warning";

        if (newStatus !== entry.data.status) {
            entry.data.status = newStatus;
            const color = getStatusColor(newStatus);
            const emissive = getEmissiveColor(newStatus);
            entry.ledMat.color.setHex(color);
            entry.accentMat.color.setHex(color);
            entry.accentMat.emissive.setHex(emissive);
            entry.baseMat.emissive.setHex(emissive);
            entry.baseMat.emissiveIntensity = newStatus === "critical" ? 0.6 : 0.15;
        }

        // Update temperature glow
        if (sensorData && sensorData.temperature) {
            const temp = sensorData.temperature;
            const t = Math.min(temp / 100, 1);
            if (currentMode === "heatmap") {
                const heatColor = new THREE.Color().setHSL(0.6 - t * 0.6, 1.0, 0.4 + t * 0.2);
                entry.baseMat.color.copy(heatColor);
                entry.baseMat.emissive.copy(heatColor);
            }
        }
    }


    // ═══════════════════════════════════════════════════════════
    // INTERACTION — hover & click
    // ═══════════════════════════════════════════════════════════

    function onMouseMove(e) {
        const rect = renderer.domElement.getBoundingClientRect();
        mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

        raycaster.setFromCamera(mouse, camera);
        const intersects = raycaster.intersectObjects(
            Object.values(machineMap).map(m => m.group),
            true
        );

        // Reset previous hover
        if (hoveredMachine && machineMap[hoveredMachine]) {
            machineMap[hoveredMachine].baseMat.emissiveIntensity =
                machineMap[hoveredMachine].data.status === "critical" ? 0.6 : 0.15;
        }

        if (intersects.length > 0) {
            let obj = intersects[0].object;
            while (obj.parent && !obj.userData.isMachine) obj = obj.parent;
            if (obj.userData.isMachine) {
                hoveredMachine = obj.name;
                const entry = machineMap[hoveredMachine];
                if (entry) entry.baseMat.emissiveIntensity = 0.5;
                renderer.domElement.style.cursor = "pointer";
            }
        } else {
            hoveredMachine = null;
            renderer.domElement.style.cursor = "default";
        }
    }

    function onMouseClick(e) {
        if (!hoveredMachine) {
            selectedMachine = null;
            hideInfoPanel();
            return;
        }
        selectedMachine = hoveredMachine;
        showInfoPanel(machineMap[selectedMachine].data);

        // Smooth zoom to machine
        const entry = machineMap[selectedMachine];
        if (entry) {
            const worldPos = new THREE.Vector3();
            entry.group.getWorldPosition(worldPos);
            smoothMoveTo(worldPos);
        }
    }

    function smoothMoveTo(target) {
        const offset = new THREE.Vector3(8, 8, 8);
        const dest = target.clone().add(offset);
        const startPos = camera.position.clone();
        const startTarget = controls.target.clone();
        let progress = 0;

        function step() {
            progress = Math.min(progress + 0.03, 1);
            const ease = easeOutCubic(progress);
            camera.position.lerpVectors(startPos, dest, ease);
            controls.target.lerpVectors(startTarget, target, ease);
            controls.update();
            if (progress < 1) requestAnimationFrame(step);
        }
        step();
    }

    function showInfoPanel(data) {
        const panel = document.getElementById("hud-info");
        if (!panel) return;

        const statusIcon = data.status === "critical" ? "🔴" :
            data.status === "warning" ? "🟡" : "🟢";

        panel.innerHTML = `
            <div class="hud-panel-header">
                <span class="hud-title">${data.twin_id}</span>
                <span class="hud-status">${statusIcon} ${data.status.toUpperCase()}</span>
            </div>
            <div class="hud-panel-body">
                <div class="hud-row"><span>Type</span><span>${data.asset_type}</span></div>
                <div class="hud-row"><span>Name</span><span>${data.name}</span></div>
                <div class="hud-row"><span>Line</span><span>${data.line}</span></div>
                <div class="hud-row"><span>Energy</span><span>${data.energy_kwh} kWh</span></div>
                <div class="hud-row"><span>OEE</span><span>${data.oee}%</span></div>
                <div class="hud-row"><span>Components</span><span>${data.components}</span></div>
                <div class="hud-row"><span>Protocol</span><span>${data.protocol || "OPC-UA"}</span></div>
            </div>
        `;
        panel.classList.add("show");
    }

    function hideInfoPanel() {
        const panel = document.getElementById("hud-info");
        if (panel) panel.classList.remove("show");
    }

    function updateHUD() {
        if (!sceneData) return;
        const stats = document.getElementById("hud-stats");
        if (!stats) return;

        const floorCount = sceneData.floors.length;
        const totalMachines = sceneData.total_machines;
        let okCount = 0, warnCount = 0, critCount = 0;
        sceneData.floors.forEach(f => f.machines.forEach(m => {
            if (m.status === "ok") okCount++;
            else if (m.status === "warning") warnCount++;
            else critCount++;
        }));

        stats.innerHTML = `
            <div class="hud-stat"><span class="hud-stat-val">${totalMachines}</span><span class="hud-stat-lbl">Machines</span></div>
            <div class="hud-stat"><span class="hud-stat-val">${floorCount}</span><span class="hud-stat-lbl">Floors</span></div>
            <div class="hud-stat ok"><span class="hud-stat-val">${okCount}</span><span class="hud-stat-lbl">Online</span></div>
            <div class="hud-stat warn"><span class="hud-stat-val">${warnCount}</span><span class="hud-stat-lbl">Warning</span></div>
            <div class="hud-stat crit"><span class="hud-stat-val">${critCount}</span><span class="hud-stat-lbl">Critical</span></div>
        `;
    }


    // ═══════════════════════════════════════════════════════════
    // RESIZE & LIFECYCLE
    // ═══════════════════════════════════════════════════════════

    function onResize() {
        if (!renderer || !canvas) return;
        const W = canvas.parentElement.clientWidth;
        const H = canvas.parentElement.clientHeight;
        camera.aspect = W / H;
        camera.updateProjectionMatrix();
        renderer.setSize(W, H);
        if (composer) composer.setSize(W, H);
    }

    function start() {
        if (!renderer) return;
        running = true;
        clock.start();
        animate();
        loadScene();
    }

    function stop() {
        running = false;
        if (animId) cancelAnimationFrame(animId);
        if (wsSensors) { try { wsSensors.close(); } catch { } }
    }

    function refresh() {
        loadScene();
    }


    // ═══════════════════════════════════════════════════════════
    // HELPERS
    // ═══════════════════════════════════════════════════════════

    function getStatusColor(status) {
        switch (status) {
            case "critical": return RED;
            case "warning": return WARN;
            default: return GREEN;
        }
    }

    function getEmissiveColor(status) {
        switch (status) {
            case "critical": return 0x5A0015;
            case "warning": return 0x4A3500;
            default: return 0x003A1A;
        }
    }

    function easeOutCubic(x) {
        return 1 - Math.pow(1 - x, 3);
    }

    function makeTextSprite(text, opts = {}) {
        const fontsize = opts.fontsize || 24;
        const canvas2d = document.createElement("canvas");
        const ctx = canvas2d.getContext("2d");
        ctx.font = `${fontsize}px 'JetBrains Mono', monospace`;
        const textWidth = ctx.measureText(text).width;

        canvas2d.width = textWidth + 20;
        canvas2d.height = fontsize + 12;

        ctx.fillStyle = opts.bgColor || "rgba(11,15,26,0.7)";
        roundRect(ctx, 0, 0, canvas2d.width, canvas2d.height, 4);
        ctx.fill();

        ctx.font = `${fontsize}px 'JetBrains Mono', monospace`;
        ctx.fillStyle = opts.color || "#CFD8E8";
        ctx.fillText(text, 10, fontsize + 2);

        const texture = new THREE.CanvasTexture(canvas2d);
        texture.needsUpdate = true;

        const spriteMat = new THREE.SpriteMaterial({
            map: texture,
            transparent: true,
            depthTest: false,
        });
        return new THREE.Sprite(spriteMat);
    }

    function roundRect(ctx, x, y, w, h, r) {
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.lineTo(x + w - r, y);
        ctx.quadraticCurveTo(x + w, y, x + w, y + r);
        ctx.lineTo(x + w, y + h - r);
        ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
        ctx.lineTo(x + r, y + h);
        ctx.quadraticCurveTo(x, y + h, x, y + h - r);
        ctx.lineTo(x, y + r);
        ctx.quadraticCurveTo(x, y, x + r, y);
        ctx.closePath();
    }


    // ═══════════════════════════════════════════════════════════
    // PUBLIC API
    // ═══════════════════════════════════════════════════════════

    return {
        init,
        start,
        stop,
        refresh,
        loadScene,
        setViewMode,
    };

})();
