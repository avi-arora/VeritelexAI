# Bucket CORS for browser uploads. Sourced by setup.sh and deploy.sh (expects their g() helper).
#
# Browsers PUT files straight to the case-files bucket with V4 signed URLs. That PUT carries two
# request headers, Content-Type and x-goog-content-length-range (the size limit GCS enforces), so
# the browser sends a CORS preflight first. GCS allows the preflight only if *every* requested
# header is listed in responseHeader. If one is missing, GCS still answers 200 but without the
# Access-Control-* headers, and every browser upload fails with an opaque "Failed to fetch".

UPLOAD_CORS_REQUEST_HEADERS="content-type,x-goog-content-length-range"

# apply_upload_cors BUCKET ORIGIN... — set the policy, then prove it with real preflights.
apply_upload_cors() {
  local bucket="$1"; shift
  local origins_json file origin attempt
  origins_json=$(printf '"%s",' "$@"); origins_json="[${origins_json%,}]"
  file="$(mktemp)"
  printf '[{"origin": %s, "method": ["PUT"], "responseHeader": ["Content-Type", "x-goog-content-length-range"], "maxAgeSeconds": 3600}]\n' \
    "${origins_json}" >"${file}"
  g storage buckets update "gs://${bucket}" --cors-file="${file}" >/dev/null
  rm -f "${file}"

  # Preflights are unauthenticated, so this checks exactly what a browser will get.
  for origin in "$@"; do
    for attempt in 1 2 3 4 5; do
      if curl -sS -o /dev/null -D - -X OPTIONS "https://storage.googleapis.com/${bucket}/cors-probe" \
          -H "Origin: ${origin}" -H "Access-Control-Request-Method: PUT" \
          -H "Access-Control-Request-Headers: ${UPLOAD_CORS_REQUEST_HEADERS}" \
          | tr -d '\r' | grep -qix "access-control-allow-origin: ${origin}"; then
        break
      fi
      if [[ "${attempt}" == 5 ]]; then
        echo "Browser uploads from ${origin} would be blocked: CORS preflight not allowed on gs://${bucket}" >&2
        return 1
      fi
      sleep 3
    done
  done

  # ...and nothing else: the policy must name exactly the app's origins (no wildcard).
  if curl -sS -o /dev/null -D - -X OPTIONS "https://storage.googleapis.com/${bucket}/cors-probe" \
      -H "Origin: https://not-allowed.invalid" -H "Access-Control-Request-Method: PUT" \
      -H "Access-Control-Request-Headers: ${UPLOAD_CORS_REQUEST_HEADERS}" \
      | tr -d '\r' | grep -qi "^access-control-allow-origin:"; then
    echo "gs://${bucket} CORS also allows origins outside the list (wildcard?)" >&2
    return 1
  fi
}
