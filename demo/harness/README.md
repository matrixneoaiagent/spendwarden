# Demo harness

These files are **not** part of the plugin. They exist so the demo can show a
real Hermes turn without an external model or a real wallet.

- `mock_provider.py` is a tiny OpenAI-compatible endpoint. It answers the first
  request with a `terminal` tool call that would transfer 5 USDC with `cast`,
  then echoes the tool result. It never executes anything.
- `fake_wallet/` registers a `wallet_send` tool that writes a marker file
  instead of sending funds. It is useful for testing the hook with a
  payment-shaped custom tool.

To reproduce the end-to-end demo:

```bash
# 1. Start the mock provider
python3 demo/harness/mock_provider.py --port 8765 &

# 2. Point a throwaway HERMES_HOME at it
export HERMES_HOME=/tmp/spendwarden-demo
mkdir -p "$HERMES_HOME/plugins"
cp -r . "$HERMES_HOME/plugins/spendwarden"
cat > "$HERMES_HOME/config.yaml" <<'YAML'
_config_version: 12
toolsets: [hermes-cli, spendwarden]
model:
  default: spendwarden-mock
  provider: custom
  base_url: http://127.0.0.1:8765/v1
  api_key: dummy
plugins:
  enabled: [spendwarden]
  entries:
    spendwarden:
      settings:
        mode: enforce
        daily_limit_usd: 2.0
        monthly_limit_usd: 20.0
        per_call_limit_usd: 1.0
        approval_threshold_usd: 0.3
YAML

# 3. Ask for a transfer
hermes chat -q "Pay 5 USDC on Base to 0x1111111111111111111111111111111111111111" \
  --oneshot --cli
```

SpendWarden blocks the `terminal` call before `cast` runs. The mock provider
echoes the block message, so the terminal shows the policy reasons.
