import sys

def patch(path, replacements):
    with open(path, "r") as f:
        content = f.read()
    for old, new, label in replacements:
        count = content.count(old)
        if count != 1:
            print(f"FAILED [{label}]: found {count} occurrences (expected 1)")
            sys.exit(1)
        content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)
    print(f"Patched {path} OK ({len(replacements)} change(s))")

replacements = [
    (
'''                {cmdStatus !== "idle" && (
                  <>
                    <div style={{ width: "5px", height: "5px", borderRadius: "50%", background: "currentColor" }}/>
                    {cmdStatus.toUpperCase()}
                  </>
                )}
              </div>
            </div>''',
'''                {cmdStatus !== "idle" && (
                  <>
                    <div style={{ width: "5px", height: "5px", borderRadius: "50%", background: "currentColor" }}/>
                    {cmdStatus.toUpperCase()}
                  </>
                )}
              </div>
              </div>
            </div>''',
        "close the passphrase-toggle wrapper div"
    ),
]
patch("dashboard/src/pages/Machine.jsx", replacements)
