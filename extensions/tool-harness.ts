/** Opt-in Pi runtime adapter. No model loop in the observational sidecar. */
import * as sdk from '@earendil-works/pi-coding-agent';
// Pi1.5's extension loader aliases the pi-ai root; subpath API imports do
// not resolve through that alias. Its official API factory avoids the alias bug.
import { lazyStream, openAICompletionsApi } from '@earendil-works/pi-ai';
import { Providers } from './tool-harness/providers.mjs';
import { harnessExtension } from './tool-harness/index.mjs';

const { streamSimple } = openAICompletionsApi();

export default async function(pi: sdk.ExtensionAPI) {
  // Reads only explicit boolean metadata, never Pi/MCP/user credential files.
  const providers = await Providers.load();
  return harnessExtension(sdk, { providers, native:{lazyStream,streamSimple} })(pi);
}
