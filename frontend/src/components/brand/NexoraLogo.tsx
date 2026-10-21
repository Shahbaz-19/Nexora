interface NexoraLogoProps {
  size?: number;
  className?: string;
  decorative?: boolean;
}

export default function NexoraLogo({
  size = 40,
  className = "",
  decorative = false,
}: NexoraLogoProps) {
  return (
    <span
      className={`nexora-logo ${className}`}
      style={{ width: size, height: size }}
      role={decorative ? undefined : "img"}
      aria-hidden={decorative || undefined}
      aria-label={decorative ? undefined : "Nexora"}
    >
      <svg viewBox="0 0 40 40" fill="none" aria-hidden="true">
        <path d="M19.6 10.3c-1.4-2.7-5.8-2.5-6.8.6-3.1.2-4.4 3.8-2.5 6-2.8 1.7-2.2 6.1.8 7.2-1 3.8 2.1 7.2 5.7 6.5.6 2.3 1.7 3.3 2.8 3.8V10.3Z" />
        <path d="M20.4 10.3c1.4-2.7 5.8-2.5 6.8.6 3.1.2 4.4 3.8 2.5 6 2.8 1.7 2.2 6.1-.8 7.2 1 3.8-2.1 7.2-5.7 6.5-.6 2.3-1.7 3.3-2.8 3.8V10.3Z" />
        <path d="M19.5 16h-4l-2-2.2M19.5 21h-5.3M19.5 26h-3.8l-2.1 2.1M20.5 14.2h4l2-2M20.5 19h5.4l2.1-2M20.5 25h4.2l2.1 2.1" />
        <circle cx="12.2" cy="12.4" r="1.25" />
        <circle cx="12.7" cy="21" r="1.25" />
        <circle cx="12.3" cy="29.3" r="1.25" />
        <circle cx="27.8" cy="11" r="1.25" />
        <circle cx="29.3" cy="15.7" r="1.25" />
        <circle cx="28.2" cy="28.4" r="1.25" />
      </svg>
    </span>
  );
}
