/** Opt-in Pi runtime adapter. No model loop in the observational sidecar. */
import * as sdk from '@earendil-works/pi-coding-agent';
import { harnessExtension } from './tool-harness/index.mjs';

export default harnessExtension(sdk);
