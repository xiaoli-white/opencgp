import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export type StoryProps = {
  title: string;
  points: string[];
  images: string[];
  brand: string;
  durationInFrames: number;
  fps: number;
  accent?: string;
};

export const DEFAULT_PROPS: StoryProps = {
  title: "Your title goes here",
  points: ["First key point", "Second key point", "Third key point"],
  images: [],
  brand: "OpenCGP",
  durationInFrames: 300,
  fps: 30,
};

const FONT_STACK =
  '"Inter", "Helvetica Neue", "PingFang SC", "Microsoft YaHei", Arial, sans-serif';

const MAX_POINTS = 6;
const MAX_IMAGES = 6;

const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value));

const ImageCard: React.FC<{
  src: string;
  frame: number;
  start: number;
  segment: number;
  isLast: boolean;
  accent: string;
}> = ({ src, frame, start, segment, isLast, accent }) => {
  const local = frame - start;
  if (local < 0) return null;
  if (!isLast && local > segment + 12) return null;

  const fadeIn = interpolate(local, [0, 14], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeOut = isLast
    ? 1
    : interpolate(local, [segment - 12, segment], [1, 0], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      });
  const opacity = Math.min(fadeIn, fadeOut);

  const scale = interpolate(local, [0, Math.max(segment, 30)], [1.04, 1.18], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.ease),
  });
  const shiftX = interpolate(local, [0, Math.max(segment, 30)], [-1.6, 1.6], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const shiftY = interpolate(local, [0, Math.max(segment, 30)], [1.2, -1.2], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ opacity }}>
      <div
        style={{
          width: "100%",
          height: "100%",
          overflow: "hidden",
          borderRadius: 26,
          border: "1px solid rgba(255,255,255,0.14)",
        }}
      >
        <Img
          src={src}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            transform: `scale(${scale}) translate(${shiftX}%, ${shiftY}%)`,
          }}
        />
      </div>
    </AbsoluteFill>
  );
};

export const Story: React.FC<StoryProps> = ({
  title,
  points,
  images,
  brand,
  accent = "#7c9cff",
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames, fps } = useVideoConfig();

  const list = (Array.isArray(points) ? points : [])
    .filter((item) => typeof item === "string" && item.trim().length > 0)
    .slice(0, MAX_POINTS);
  const gallery = (Array.isArray(images) ? images : [])
    .filter((item) => typeof item === "string" && item.trim().length > 0)
    .slice(0, MAX_IMAGES);
  const hasImages = gallery.length > 0;

  const brandStart = Math.max(Math.round(durationInFrames * 0.78), durationInFrames - 3 * fps);
  const titleStart = 4;
  const pointStart = Math.round(fps * 1.1);
  const pointStagger = list.length > 0
    ? Math.max(10, Math.min(Math.round(fps * 0.55), Math.floor((brandStart - pointStart) / (list.length + 1))))
    : 0;

  const titleOpacity = interpolate(frame, [titleStart, titleStart + 26], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const titleLift = interpolate(frame, [titleStart, titleStart + 30], [46, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });

  const brandOpacity = interpolate(frame, [brandStart, brandStart + 20], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const brandLift = interpolate(frame, [brandStart, brandStart + 24], [18, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });

  const imageStart = Math.round(fps * 0.9);
  const imageWindow = Math.max(brandStart - imageStart, fps);
  const segment = gallery.length > 0 ? Math.floor(imageWindow / gallery.length) : imageWindow;

  const pointSize = list.length >= 5 ? 19 : list.length === 4 ? 20 : 22;

  const progress = clamp(frame / Math.max(durationInFrames - 1, 1), 0, 1);

  return (
    <AbsoluteFill style={{ backgroundColor: "#070b16", fontFamily: FONT_STACK }}>
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(160deg, #0b1226 0%, #0a1124 46%, #070b16 100%)",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: 560,
          height: 720,
          background: `linear-gradient(180deg, ${accent}22 0%, rgba(7,11,22,0) 78%)`,
        }}
      />

      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          alignItems: "stretch",
          gap: 40,
          padding: "64px 72px 72px",
          boxSizing: "border-box",
        }}
      >
        <div
          style={{
            flex: hasImages ? "1.08 1 0" : "1 1 0",
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            minWidth: 0,
          }}
        >
          <div
            style={{
              opacity: titleOpacity,
              transform: `translateY(${titleLift}px)`,
            }}
          >
            <div
              style={{
                width: 74,
                height: 4,
                borderRadius: 999,
                background: accent,
                marginBottom: 22,
              }}
            />
            <h1
              style={{
                margin: 0,
                fontSize: title.length > 46 ? 44 : 52,
                lineHeight: 1.14,
                fontWeight: 700,
                letterSpacing: "-0.02em",
                color: "#f4f7ff",
                maxWidth: hasImages ? 560 : 1000,
              }}
            >
              {title}
            </h1>
          </div>

          <div style={{ marginTop: 34, display: "flex", flexDirection: "column", gap: 16 }}>
            {list.map((point, index) => {
              const start = pointStart + index * pointStagger;
              const opacity = interpolate(frame, [start, start + 20], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              });
              const lift = interpolate(frame, [start, start + 24], [26, 0], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
                easing: Easing.out(Easing.cubic),
              });
              return (
                <div
                  key={`${index}-${point.slice(0, 12)}`}
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 14,
                    opacity,
                    transform: `translateY(${lift}px)`,
                  }}
                >
                  <span
                    style={{
                      flex: "0 0 auto",
                      marginTop: 3,
                      width: 26,
                      height: 26,
                      borderRadius: 9,
                      background: "rgba(124,156,255,0.16)",
                      border: `1px solid ${accent}55`,
                      color: "#cdd9ff",
                      fontSize: 13,
                      fontWeight: 700,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    {index + 1}
                  </span>
                  <p
                    style={{
                      margin: 0,
                      fontSize: pointSize,
                      lineHeight: 1.5,
                      color: "#c9d4ea",
                      maxWidth: hasImages ? 520 : 980,
                    }}
                  >
                    {point}
                  </p>
                </div>
              );
            })}
          </div>
        </div>

        {hasImages ? (
          <div
            style={{
              flex: "0.92 1 0",
              position: "relative",
              minWidth: 0,
              opacity: interpolate(frame, [imageStart - 8, imageStart + 12], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              }),
            }}
          >
            {gallery.map((src, index) => (
              <ImageCard
                key={`${index}-${src.slice(-24)}`}
                src={src}
                frame={frame}
                start={imageStart + index * segment}
                segment={segment}
                isLast={index === gallery.length - 1}
                accent={accent}
              />
            ))}
          </div>
        ) : null}
      </div>

      <div
        style={{
          position: "absolute",
          left: 72,
          right: 72,
          bottom: 34,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          opacity: brandOpacity,
          transform: `translateY(${brandLift}px)`,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span
            style={{
              width: 9,
              height: 9,
              borderRadius: 999,
              background: accent,
            }}
          />
          <span
            style={{
              fontSize: 15,
              fontWeight: 600,
              letterSpacing: "0.16em",
              textTransform: "uppercase",
              color: "#e8eeff",
            }}
          >
            {brand}
          </span>
        </div>
      </div>

      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          height: 3,
          backgroundColor: "rgba(255,255,255,0.06)",
        }}
      >
        <div
          style={{
            width: `${progress * 100}%`,
            height: "100%",
            background: `linear-gradient(90deg, ${accent}00, ${accent})`,
          }}
        />
      </div>
    </AbsoluteFill>
  );
};
