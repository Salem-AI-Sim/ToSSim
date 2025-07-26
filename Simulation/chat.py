from enum import Enum, auto
from typing import TYPE_CHECKING, Dict, List, Tuple, Union
import time # Import time for timestamping
if TYPE_CHECKING:
    from .player import Player
    from .enums import Time

class ChannelOpenState(Enum):
    READ = auto()
    WRITE = auto()

class ChatChannelType(Enum):
    DAY_PUBLIC = auto()
    MAFIA_NIGHT = auto()
    COVEN_NIGHT = auto()
    VAMPIRE_NIGHT = auto()
    JAILED = auto()
    DEAD = auto()
    WHISPER = auto()  # one-off dynamic channels; key = (src_id,dst_id,day)
    MEDIUM_SEANCE = auto()  # Medium-dead player communication
    PLAYER_PRIVATE_NOTIFICATION = auto() # For player-specific notifications (e.g., roleblocked, doused)

class ChatMessage:
    _message_counter = 0 # For deterministic temporal sorting

    def __init__(self, sender: 'Player', message: str, channel_type: ChatChannelType, *, is_environment: bool = False):
        self.sender = sender
        self.message = message
        self.channel_type = channel_type
        self.is_environment = is_environment  # True for system/death messages
        self.timestamp = ChatMessage._message_counter # Use a counter for deterministic order
        ChatMessage._message_counter += 1

    def __repr__(self):
        prefix = "[ENV]" if self.is_environment else f"[{self.channel_type.name}]"
        sender_name = "SYSTEM" if self.is_environment else self.sender.name
        return f"{prefix} {sender_name}: {self.message}"

class ChatChannel:
    """Light wrapper holding message history and r/w flags."""
    def __init__(self, channel_type: ChatChannelType):
        self.channel_type = channel_type
        self.messages: List[ChatMessage] = []
        # open state per player_id: {id: {READ, WRITE}}
        self.members: Dict[int, set[ChannelOpenState]] = {}

    # ------------------------------------------------------------------
    def add_member(self, player: 'Player', *, can_write: bool = True, can_read: bool = True):
        states = set()
        if can_read:
            states.add(ChannelOpenState.READ)
        if can_write:
            states.add(ChannelOpenState.WRITE)
        self.members.setdefault(player.id, set()).update(states)

    def remove_member(self, player: 'Player'):
        self.members.pop(player.id, None)

    def broadcast(self, sender: 'Player', text: str, *, is_environment: bool = False):
        self.messages.append(ChatMessage(sender, text, self.channel_type, is_environment=is_environment))

    def get_visible(self, player: 'Player') -> List[ChatMessage]:
        if ChannelOpenState.READ not in self.members.get(player.id, set()):
            return []
        return self.messages

class ChatPeriod:
    """Stores chat history for a specific day/night period."""
    def __init__(self, day: int, is_night: bool):
        self.day = day
        self.is_night = is_night
        self.messages: List[ChatMessage] = []
        self.whispers: List[ChatMessage] = []

    def add_message(self, message: ChatMessage):
        if message.channel_type == ChatChannelType.WHISPER:
            self.whispers.append(message)
        else:
            self.messages.append(message)

    def get_period_name(self) -> str:
        return f"Night {self.day}" if self.is_night else f"Day {self.day}"

class ChatManager:
    def __init__(self, all_players=None, logger=None):
        # Store reference to all players for blackmailer whisper access
        self._all_players = all_players or []
        # Store reference to logger for chat logging
        self.logger = logger
        # Static channels
        self.channels: Dict[ChatChannelType, ChatChannel] = {t: ChatChannel(t) for t in ChatChannelType if t not in [ChatChannelType.WHISPER, ChatChannelType.PLAYER_PRIVATE_NOTIFICATION]}
        # dynamic whispers: key -> ChatChannel
        self.whispers: List[ChatMessage] = []
        
        # dynamic seances: key = (medium_id, target_id, day) -> ChatChannel
        self.seances: List[ChatMessage] = []
        
        # dynamic player-specific notification channels: key = player_id -> ChatChannel
        self.player_notifications_channels: Dict[int, ChatChannel] = {}
        
        # Historical chat storage: key = (day, is_night) -> ChatHistory
        self.history: Dict[Tuple[int, bool], ChatPeriod] = {}
        
        # Current period tracking
        self.current_day: int = 0
        self.current_is_night: bool = False

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------
    def start_new_period(self, day: int, is_night: bool):
        """Start a new day/night period, preserving all chat history."""
        # Update current period
        self.current_day = day
        self.current_is_night = is_night
        
        # Create new period key
        period_key = (day, is_night)
        
        # Initialize new period if it doesn't exist
        if period_key not in self.history:
            self.history[period_key] = ChatPeriod(day, is_night)
        
        # Clear current period's messages (but keep them in history)
        for channel in self.channels.values():
            channel.messages.clear()
        self.whispers.clear()
        self.seances.clear()

    def get_full_chat_history(self, actor=None):
        """Return the full chat history as a string, optionally filtered for an actor (for visibility rules)."""
        history = []
        for channel in self.channels.values():
            for msg in channel.messages:
                # Optionally filter by actor visibility if needed
                if actor is None or self._message_is_visible_to(msg, actor):
                    history.append(str(msg))
        # Add whispers and seances if needed
        for msg in self.whispers:
            if actor is None or self._message_is_visible_to(msg, actor):
                history.append(str(msg))
        for msg in self.seances:
            if actor is None or self._message_is_visible_to(msg, actor):
                history.append(str(msg))
        return '\n'.join(history) if history else "No visible messages."

    def get_full_chat_history_by_phase(self):
        """Return the full chat history, split by phase (day/night), as a list of (day, is_night, messages) tuples."""
        # We'll assume self.channels['main'] contains the main chat log
        # and that each message has a .day and .is_night attribute
        history = {}
        for msg in self.channels['main'].messages:
            key = (msg.day, msg.is_night)
            if key not in history:
                history[key] = []
            history[key].append(msg)
        # Return sorted by (day, is_night)
        return [ (day, is_night, history[(day, is_night)]) for (day, is_night) in sorted(history.keys()) ]

    def _player_could_see_channel(self, player: 'Player', channel_type: ChatChannelType, day: int, is_night: bool) -> bool:
        """Determine if a player could see a channel during a specific period."""
        if not player.is_alive:
            return channel_type == ChatChannelType.DEAD
        
        if channel_type == ChatChannelType.DAY_PUBLIC:
            return True  # All living players can see day public
        elif channel_type == ChatChannelType.DEAD:
            return player.role.name.value == "Medium"  # Only mediums can see dead chat
        elif channel_type == ChatChannelType.MAFIA_NIGHT:
            return is_night and player.role.faction.name == "MAFIA"
        elif channel_type == ChatChannelType.COVEN_NIGHT:
            return is_night and player.role.faction.name == "COVEN"
        elif channel_type == ChatChannelType.VAMPIRE_NIGHT:
            return is_night and player.role.faction.name == "VAMPIRE"
        elif channel_type == ChatChannelType.JAILED:
            return False  # Jail messages are private to that night only
        elif channel_type == ChatChannelType.MEDIUM_SEANCE:
            return False  # Seance messages are handled separately like whispers
        elif channel_type == ChatChannelType.PLAYER_PRIVATE_NOTIFICATION:
            return False  # Private notifications are handled separately in get_visible_messages
        
        return False

    def _get_whisper_participants(self, whisper: ChatMessage) -> List[int]:
        """Extract participant IDs from a whisper message (placeholder)."""
        # This would need to be enhanced to track whisper participants properly
        return []

    # ------------------------------------------------------------------
    # Environment message helpers
    # ------------------------------------------------------------------
    def add_environment_message(self, message: str, channel_type: ChatChannelType = ChatChannelType.DAY_PUBLIC):
        """Add a system/environment message to the specified channel."""
        # Create a dummy player for environment messages
        env_player = type('EnvironmentPlayer', (), {'name': 'SYSTEM', 'id': -1})()
        channel = self.channels[channel_type]
        channel.broadcast(env_player, message, is_environment=True)

    # ------------------------------------------------------------------
    # Membership helpers
    # ------------------------------------------------------------------
    def move_player_to_channel(self, player: 'Player', channel_type: ChatChannelType, *, write: bool = True, read: bool = True):
        # ensure channel exists
        if channel_type == ChatChannelType.WHISPER:
            raise ValueError("WHISPER channels are dynamic; use create_whisper_channel")
        chan = self.channels[channel_type]
        chan.add_member(player, can_write=write, can_read=read)

    def remove_player_from_channel(self, player: 'Player', channel_type: ChatChannelType):
        chan = self.channels.get(channel_type)
        if chan:
            chan.remove_member(player)

    # ------------------------------------------------------------------
    # Speaking APIs
    # ------------------------------------------------------------------
    def send_speak(self, player: 'Player', text: str) -> Union[ChatMessage, str]:
        """Send a public message from a player."""
        # Check if player can write to DAY_PUBLIC
        if ChannelOpenState.WRITE not in self.channels[ChatChannelType.DAY_PUBLIC].members.get(player.id, set()):
            return "You cannot speak right now."
        
        # Create and broadcast the message
        message = ChatMessage(player, text, ChatChannelType.DAY_PUBLIC)
        self.channels[ChatChannelType.DAY_PUBLIC].broadcast(player, text)
        
        # Log the chat message if logger is available
        if self.logger:
            turn_name = f"Night {self.current_day}" if self.current_is_night else f"Day {self.current_day}"
            self.logger.log_chat(player.name, text, turn_name, is_whisper=False)
        
        return message

    def send_whisper(self, src: 'Player', dst: 'Player', text: str, *, day: int, is_night: bool) -> Union[ChatMessage, str]:
        """Send a whisper from src to dst."""
        # Create whisper key
        whisper_key = (min(src.id, dst.id), max(src.id, dst.id), day)
        
        # Find existing whisper channel or create new one
        whisper_channel = None
        for channel in self.channels.values():
            if (channel.channel_type == ChatChannelType.WHISPER and 
                src in channel.members and dst in channel.members):
                whisper_channel = channel
                break
        
        if not whisper_channel:
            # Create new whisper channel
            whisper_channel = ChatChannel(ChatChannelType.WHISPER)
            whisper_channel.add_member(src, can_write=True, can_read=True)
            whisper_channel.add_member(dst, can_write=True, can_read=True)
            self.whispers.append(ChatMessage(src, f"--- New Whisper Channel: Day {day} ---", ChatChannelType.WHISPER)) # Add marker for new whisper
        
        # Send the whisper
        message = ChatMessage(src, text, ChatChannelType.WHISPER)
        whisper_channel.broadcast(src, text)
        
        # Log the whisper if logger is available
        if self.logger:
            turn_name = f"Night {day}" if is_night else f"Day {day}"
            self.logger.log_chat(src.name, text, turn_name, is_whisper=True)
        
        return message

    def create_seance_channel(self, medium: 'Player', target: 'Player'):
        """Create a seance channel between Medium and target."""
        key = (medium.id, target.id, self.current_day)
        
        if key in self.seances:
            return  # Seance already exists
        
        # Create new seance channel
        channel = ChatChannel(ChatChannelType.MEDIUM_SEANCE)
        
        # Add both players to the seance
        channel.add_member(medium, can_write=True, can_read=True)
        channel.add_member(target, can_write=True, can_read=True)
        
        self.seances.append(ChatMessage(medium, f"--- New Seance Channel: Day {self.current_day} ---", ChatChannelType.MEDIUM_SEANCE)) # Add marker for new seance
        
        # Add environment message to announce seance
        channel.broadcast(medium, f"[SEANCE] {medium.name} has initiated a seance with {target.name}.", is_environment=True)
        
        print(f"[Chat] Seance channel created between {medium.name} (Medium) and {target.name}")

    def send_seance(self, sender: 'Player', text: str) -> Union[ChatMessage, str]:
        """Send a message in the seance channel this player is part of."""
        # Find seance channel this player is in
        for channel in self.channels.values():
            if (channel.channel_type == ChatChannelType.MEDIUM_SEANCE and 
                sender in channel.members):
                channel.broadcast(sender, text)
                return channel.messages[-1]
        
        return "You are not in any active seance."

    # ------------------------------------------------------------------
    # Player-specific notification API
    # ------------------------------------------------------------------
    def add_player_notification(self, player: 'Player', message: str, *, is_environment: bool = False):
        """Add a private notification message visible only to a specific player."""
        if player.id not in self.player_notifications_channels:
            self.player_notifications_channels[player.id] = ChatChannel(ChatChannelType.PLAYER_PRIVATE_NOTIFICATION)
        
        channel = self.player_notifications_channels[player.id]
        # Use a dummy sender for environment-like notifications, or the player themselves for self-generated ones
        sender_for_notification = type('NotificationSender', (), {'name': 'SYSTEM', 'id': -2})() if is_environment else player
        channel.broadcast(sender_for_notification, message, is_environment=is_environment)

    # ------------------------------------------------------------------
    def get_visible_messages(self, player: 'Player') -> List[ChatMessage]:
        """Get all currently visible messages for a player (current period only)."""
        msgs: List[ChatMessage] = []
        for chan in self.channels.values():
            msgs.extend(chan.get_visible(player))
        
        # Add whispers that this player is part of
        for msg in self.whispers:
            if msg.sender == player or (hasattr(msg, 'recipient') and msg.recipient == player):
                msgs.append(msg)
        
        # Add seances that this player is part of
        for msg in self.seances:
            if msg.sender == player or (hasattr(msg, 'recipient') and msg.recipient == player):
                msgs.append(msg)
        
        # Add player-specific notifications
        if player.id in self.player_notifications_channels:
            msgs.extend(self.player_notifications_channels[player.id].messages)

        # order by timestamp
        return sorted(msgs, key=lambda msg: msg.timestamp)

    def get_current_player_notifications(self, player: 'Player') -> List[ChatMessage]:
        """Get all private notifications for a player for the current period."""
        if player.id in self.player_notifications_channels:
            return sorted(self.player_notifications_channels[player.id].messages, key=lambda msg: msg.timestamp)
        return [] 

    def get_multi_period_chat_history(self, actor, day, is_night):
        """Return the full chat history, split by phase, but never truncated."""
        history = []
        for channel in self.channels.values():
            for msg in channel.messages:
                history.append(str(msg))
        if self.whispers:
            for msg in self.whispers:
                history.append(str(msg))
        if self.seances:
            for msg in self.seances:
                history.append(str(msg))
        if not history:
            return "No visible messages."
        return "\n".join(history)

    def get_all_chat_history(self, player=None):
        """Return the full chat history for the player (or all players if None), including all channels, whispers, and seances."""
        all_msgs = []
        for channel in self.channels.values():
            all_msgs.extend(channel.messages)
        all_msgs.extend(self.whispers)
        all_msgs.extend(self.seances)
        # Optionally, sort by timestamp if available
        all_msgs.sort(key=lambda m: getattr(m, 'timestamp', 0))
        if not all_msgs:
            return "No visible messages."
        return "\n".join(str(m) for m in all_msgs) 