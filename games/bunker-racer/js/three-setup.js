// three.js r160 + the addons the game uses, exposed as the THREE global for the classic scripts.
// Loaded through the import map in index.html, and bundled into Bunker-0.html by tools/build_standalone.mjs.
import * as T from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

window.THREE = Object.assign({}, T, { EffectComposer, RenderPass, UnrealBloomPass, OutputPass, ShaderPass, GLTFLoader });
