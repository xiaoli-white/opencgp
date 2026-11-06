import { Composition } from "remotion";
import { Story, DEFAULT_PROPS, type StoryProps } from "./Story";

const MIN_DURATION = 60;
const MAX_DURATION = 1800;
const MIN_FPS = 15;
const MAX_FPS = 60;

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="OpenCGPStory"
      component={Story}
      durationInFrames={DEFAULT_PROPS.durationInFrames}
      fps={DEFAULT_PROPS.fps}
      width={1280}
      height={720}
      defaultProps={DEFAULT_PROPS}
      calculateMetadata={({ props }) => {
        const typed = props as StoryProps;
        const duration = Number(typed.durationInFrames);
        const fps = Number(typed.fps);
        return {
          durationInFrames: Number.isFinite(duration)
            ? Math.min(MAX_DURATION, Math.max(MIN_DURATION, Math.round(duration)))
            : DEFAULT_PROPS.durationInFrames,
          fps: Number.isFinite(fps)
            ? Math.min(MAX_FPS, Math.max(MIN_FPS, Math.round(fps)))
            : DEFAULT_PROPS.fps,
          props: typed,
        };
      }}
    />
  );
};
