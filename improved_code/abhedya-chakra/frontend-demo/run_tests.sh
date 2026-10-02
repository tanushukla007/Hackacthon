#!/usr/bin/env bash
# Both demo-UI test suites. Run from frontend-demo/:  bash run_tests.sh
#
# Playwright cannot run in this sandbox, so the UI is tested two ways:
#   graph.render.test.jsx  SSR markup assertions (react-dom/server, CJS bundle)
#   app.dom.test.jsx       real DOM via jsdom against a stubbed backend (ESM bundle)
cd "$(dirname "$0")"
E=./node_modules/.bin/esbuild
[ -d node_modules/jsdom ] || npm install --no-save --no-audit --no-fund jsdom >/dev/null

echo "--- SSR render tests"
$E test/graph.render.test.jsx --bundle --platform=node --format=cjs --jsx=automatic \
   --outfile=./.t1.cjs --log-level=error
node .t1.cjs; A=$?; rm -f .t1.cjs

echo
echo "--- DOM behaviour tests"
$E test/app.dom.test.jsx --bundle --platform=node --format=esm --jsx=automatic \
   --outfile=./.t2.mjs --log-level=error --external:jsdom
node .t2.mjs; B=$?; rm -f .t2.mjs

exit $(( A | B ))
