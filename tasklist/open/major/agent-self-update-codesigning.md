Title: Automated remote-agent self-update, gated on a code-signing certificate
Prio:  11

Goal:  animeexpedition-agent.exe updates itself automatically (reading AGENT_LATEST_VERSION from the
       backend) instead of requiring the operator to distribute updates manually, without triggering
       Windows SmartScreen/user-trust warnings.
Open:  Blocked on the user obtaining an operator-provided code-signing certificate for the agent
       binary (remote/DEPLOY.md section 9, "Agent distribution and updates" - self-update is
       intentionally not implemented until then); nothing to implement until that certificate exists.
       Cloud deployment itself (domain + TLS) is already done and live, see
       [[remote-deploy-server-access]] in memory, so that part of the old "remaining work" note in
       CLAUDE.md no longer applies.
