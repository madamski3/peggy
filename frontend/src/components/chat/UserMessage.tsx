import type { ChatMessage } from "../../types/chat";

interface Props {
  message: ChatMessage;
}

export default function UserMessage({ message }: Props) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[75%] rounded-2xl rounded-br-md bg-primary-600 px-4 py-2.5 text-sm text-white whitespace-pre-wrap">
        {message.content}
      </div>
    </div>
  );
}
