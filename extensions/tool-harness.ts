/** Opt-in Pi runtime adapter. No model loop in the observational sidecar. */
import * as sdk from '@earendil-works/pi-coding-agent';
import { lazyStream } from '@earendil-works/pi-ai';
import { streamSimple } from '@earendil-works/pi-ai/api/openai-completions';
import { Providers } from './tool-harness/providers.mjs';
import { harnessExtension } from './tool-harness/index.mjs';

export default async function(pi: sdk.ExtensionAPI) {
  // Reads only explicit boolean metadata, never Pi/MCP/user credential files.
  const providers = await Providers.load();
  return harnessExtension(sdk, { providers, native:{lazyStream,streamSimple} })(pi);
}
