"use client";

import * as React from "react";
import { Boxes } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SmeGalaxy, type GalaxyPoint } from "@/components/three/sme-galaxy";

/** The 3D instructor galaxy behind a "3D view" toggle — OFF by default; the table is the
 *  product, the galaxy is for exploring. Nothing from three.js loads until it is switched on. */
export function GalaxyToggle({ points, query }: { points: GalaxyPoint[]; query: string }) {
  const [on, setOn] = React.useState(false);
  return (
    <div data-print-hide>
      <div className="mb-3 flex justify-end">
        <Button variant={on ? "secondary" : "outline"} size="sm" aria-pressed={on} onClick={() => setOn((v) => !v)}>
          <Boxes aria-hidden /> 3D view
        </Button>
      </div>
      {on && <SmeGalaxy points={points} query={query} />}
    </div>
  );
}
