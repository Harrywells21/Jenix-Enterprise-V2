/**
 * JENIX Skeleton Loader Components
 * Shows animated placeholders while data loads.
 */

function SkeletonBox({ width="100%", height="20px",
                        radius="6px", style={} }) {
  return (
    <div style={{
      width, height,
      borderRadius: radius,
      background: "linear-gradient(90deg, #1a1a2e 25%, #2a2a3e 50%, #1a1a2e 75%)",
      backgroundSize: "200% 100%",
      animation: "shimmer 1.5s infinite",
      ...style
    }}/>
  );
}

export function SkeletonCard() {
  return (
    <div style={{
      background:"#13131f", border:"1px solid #2a2a3e",
      borderRadius:"12px", padding:"20px"
    }}>
      <div style={{ display:"flex", justifyContent:"space-between",
                    marginBottom:"16px" }}>
        <div>
          <SkeletonBox width="140px" height="16px"
                       style={{ marginBottom:"8px" }}/>
          <SkeletonBox width="100px" height="12px"/>
        </div>
        <SkeletonBox width="60px" height="22px" radius="20px"/>
      </div>
      {[1,2,3].map(i => (
        <div key={i} style={{ marginBottom:"10px" }}>
          <div style={{ display:"flex", justifyContent:"space-between",
                        marginBottom:"4px" }}>
            <SkeletonBox width="40px" height="10px"/>
            <SkeletonBox width="30px" height="10px"/>
          </div>
          <SkeletonBox height="6px" radius="3px"/>
        </div>
      ))}
      <div style={{ display:"flex", gap:"6px", marginTop:"12px" }}>
        {[1,2,3].map(i => (
          <SkeletonBox key={i} height="28px" radius="6px"
                       style={{ flex:1 }}/>
        ))}
      </div>
    </div>
  );
}

export function SkeletonTable({ rows=5 }) {
  return (
    <div style={{
      background:"#13131f", border:"1px solid #2a2a3e",
      borderRadius:"12px", overflow:"hidden"
    }}>
      {/* Header */}
      <div style={{ background:"#0d0d1a", padding:"12px 16px",
                    display:"flex", gap:"16px",
                    borderBottom:"1px solid #2a2a3e" }}>
        {[120,80,100,80,60].map((w,i) => (
          <SkeletonBox key={i} width={`${w}px`} height="12px"/>
        ))}
      </div>
      {/* Rows */}
      {Array.from({length:rows}).map((_,i) => (
        <div key={i} style={{
          padding:"12px 16px", display:"flex", gap:"16px",
          borderBottom: i<rows-1 ? "1px solid #1a1a2e" : "none",
          background: i%2===0 ? "transparent" : "#0a0a14"
        }}>
          {[120,80,100,80,60].map((w,j) => (
            <SkeletonBox key={j} width={`${w}px`} height="12px"/>
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonStat() {
  return (
    <div style={{
      background:"#13131f", border:"1px solid #2a2a3e",
      borderRadius:"12px", padding:"20px"
    }}>
      <div style={{ display:"flex", justifyContent:"space-between",
                    marginBottom:"12px" }}>
        <SkeletonBox width="80px" height="12px"/>
        <SkeletonBox width="24px" height="24px" radius="4px"/>
      </div>
      <SkeletonBox width="80px" height="32px"
                   style={{ marginBottom:"8px" }}/>
      <SkeletonBox width="120px" height="10px"/>
    </div>
  );
}

export function SkeletonGraph() {
  return (
    <div style={{
      background:"#13131f", border:"1px solid #2a2a3e",
      borderRadius:"10px", padding:"16px"
    }}>
      <SkeletonBox width="80px" height="12px"
                   style={{ marginBottom:"12px" }}/>
      <SkeletonBox width="100%" height="120px" radius="4px"/>
    </div>
  );
}

// Inject keyframe animation once
if (typeof document !== "undefined") {
  const style = document.createElement("style");
  style.textContent = `
    @keyframes shimmer {
      0%   { background-position: 200% 0; }
      100% { background-position: -200% 0; }
    }
  `;
  if (!document.head.querySelector("#jenix-skeleton-style")) {
    style.id = "jenix-skeleton-style";
    document.head.appendChild(style);
  }
}

export default SkeletonBox;
