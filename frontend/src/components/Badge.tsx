import { statusTone } from '../utils/format';

interface BadgeProps {
  value: string;
}

export function Badge({ value }: BadgeProps) {
  return <span className={`badge badge-${statusTone(value)}`}>{value}</span>;
}
