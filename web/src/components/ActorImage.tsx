import React from "react";
import { Actor } from "../providers/mysteryContext";
import { Avatar } from "@mantine/core";
import { resolveAvatarSrc } from "../utils/avatarUtils";

interface Props {
  actor: Actor;
}

export default function ActorImage({ actor }: Props) {
  return (
    <Avatar
      src={resolveAvatarSrc(actor.image)}
      size={50}
      radius="xl"
      color="cyan"
      alt={actor.name}
    >{actor.name.slice(0, 1)}</Avatar>
  );
}
