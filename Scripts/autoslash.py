@nightyScript(
    name="Custom Command Runner",
    author="Luxed",
    description="Runs user-defined custom commands in specified channels via a UI.",
    usage="UI Script"
)
def custom_command_runner_script():
    import json
    import asyncio
    import random
    import time
    from pathlib import Path
    import aiohttp
    from datetime import datetime
    from datetime import time as datetime_time
    from discord import Webhook, Embed
    import os
    import shlex
    import re
    import traceback

    # --- Helper functions ---
    CCR_JSON_DIR = Path(getScriptsPath()) / "json"
    CCR_CHANNELS_FILE = CCR_JSON_DIR / "ccr_channels.json"
    CCR_STATE_FILE = CCR_JSON_DIR / "ccr_state.json"
    CCR_JSON_DIR.mkdir(parents=True, exist_ok=True)
    
    def ccr_clear_log():
        log_file = os.path.join(getScriptsPath(), "logs", "ccr.log")
        try:
            if os.path.exists(log_file):
                with open(log_file, "w", encoding="utf-8") as f:
                    f.write("")
        except Exception as e:
            print(f"Error clearing log file: {e}")
    
    ccr_clear_log()

    def ccr_parse_time_to_seconds(time_str):
        if not time_str or not isinstance(time_str, str):
            return None
            
        time_str = time_str.strip().lower()
        
        if time_str.isdigit():
            return int(time_str)
            
        # Parse time units
        match = re.match(r'^(\d+)([smhdw])$', time_str)
        if not match:
            return None
            
        value, unit = match.groups()
        value = int(value)
        
        multipliers = {
            's': 1,
            'm': 60,
            'h': 3600,
            'd': 86400,
            'w': 604800
        }
        
        return value * multipliers.get(unit, 1)

    def ccr_channel_id_string(channel_id):
        if channel_id is None:
            return None
        return str(channel_id)

    def ccr_is_within_timer(timer_config):
        """Check if current time is within the configured timer"""
        if not timer_config or not timer_config.get("enabled", False):
            return True
        
        now = datetime.now()
        current_time = now.time()
        current_weekday = now.weekday()
        
        allowed_days = timer_config.get("days", [])
        if allowed_days:
            weekday_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            current_day_name = weekday_names[current_weekday]
            if current_day_name not in [day.lower() for day in allowed_days]:
                return False
        
        start_time_str = timer_config.get("start_time")
        end_time_str = timer_config.get("end_time")
        
        if start_time_str and end_time_str:
            try:
                start_time = datetime_time.fromisoformat(start_time_str)
                end_time = datetime_time.fromisoformat(end_time_str)
                
                if start_time <= end_time:
                    return start_time <= current_time <= end_time
                else:
                    return current_time >= start_time or current_time <= end_time
            except ValueError:
                return True
        
        return True

    async def ccr_load_json_data(file_path, default_data):
        if not file_path.exists():
            await ccr_save_json_data(file_path, default_data)
            return default_data
        
        def _blocking_load():
            try:
                with file_path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return default_data

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _blocking_load)

    class SafeJSONEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (asyncio.Task, asyncio.Lock, asyncio.Event)):
                return f"<{type(obj).__name__} object>"
            try:
                return super().default(obj)
            except TypeError:
                return str(obj)

    async def ccr_save_json_data(file_path, data):
        def _blocking_save():
            try:
                with file_path.open("w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, cls=SafeJSONEncoder)
            except Exception as e:
                print(f"[CommandRunner] Error saving {file_path.name}: {e}")
        
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _blocking_save)
    
    async def ccr_disable_command_automatically(channel_id, command_name, bot_id, debug_mode=False):
        """Disable a command automatically when it's not found"""
        try:
            channels_cfg = await ccr_load_json_data(CCR_CHANNELS_FILE, {"channels": {}})
            
            channel_id = ccr_channel_id_string(channel_id)
            if channel_id in channels_cfg.get("channels", {}):
                channel_commands = channels_cfg["channels"][channel_id].get("commands", [])
                
                # Find and disable the specific command
                command_found = False
                for cmd in channel_commands:
                    cmd_name = cmd.get("name", "")
                    cmd_main = cmd_name.split()[0] if cmd_name else ""
                    cmd_bot_id = cmd.get("bot_id")
                    
                    if (cmd_main == command_name and 
                        str(cmd_bot_id) == str(bot_id) and 
                        cmd.get("command_type") == "slash"):
                        
                        cmd["enabled"] = False
                        command_found = True
                        break
                
                await ccr_save_json_data(CCR_CHANNELS_FILE, channels_cfg)
                
                if hasattr(bot, '_command_runner_manager') and bot._command_runner_manager:
                    manager = bot._command_runner_manager
                    if hasattr(manager, 'channels_cfg'):
                        manager.channels_cfg = channels_cfg
                
                if command_found:
                    ccr_log_to_file(f"🔴 AUTO-DISABLED: Command '{command_name}' has been automatically disabled" + "\n", debug_mode=debug_mode, important=True)
                
                return command_found
            else:
                ccr_log_to_file(f"❌ AUTO-DISABLE: Channel '{channel_id}' not found in configuration", level="ERROR", debug_mode=debug_mode)
        except Exception as e:
            ccr_log_to_file(f"Error auto-disabling command: {e}", level="ERROR", debug_mode=debug_mode)
            return False
        return False
    
    async def ccr_save_slash_type_to_config(channel_id, command_name, bot_id, command_type, debug_mode=False):
        """Save slash command type directly to ccr_channels.json"""
        try:
            channels_cfg = await ccr_load_json_data(CCR_CHANNELS_FILE, {"channels": {}})
            
            if channel_id in channels_cfg.get("channels", {}):
                channel_commands = channels_cfg["channels"][channel_id].get("commands", [])
                
                # Find and update the specific command
                for i, cmd in enumerate(channel_commands):
                    cmd_name = cmd.get("name", "")
                    cmd_main = cmd_name.split()[0] if cmd_name else ""
                    cmd_bot_id = cmd.get("bot_id")
                    cmd_type = cmd.get("command_type")
                    
                    if (cmd_main == command_name and 
                        str(cmd_bot_id) == str(bot_id) and 
                        cmd_type == "slash"):
                        cmd["slash_type"] = command_type
                        ccr_log_to_file(f"Updated slash_type for command '{cmd_name}' (main: '{command_name}') -> {command_type}", level="SUCCESS", debug_mode=debug_mode)
                        break
                await ccr_save_json_data(CCR_CHANNELS_FILE, channels_cfg)
        except Exception as e:
            ccr_log_to_file(f"Error saving slash_type to config: {e}", debug_mode=debug_mode)
    
    async def ccr_save_execution_type_to_config(channel_id, command_name, bot_id, execution_type, debug_mode=False):
        """Save execution type (direct/api) to ccr_channels.json"""
        try:
            channels_cfg = await ccr_load_json_data(CCR_CHANNELS_FILE, {"channels": {}})
            
            if channel_id in channels_cfg.get("channels", {}):
                channel_commands = channels_cfg["channels"][channel_id].get("commands", [])
                
                # Find and update the specific command
                for i, cmd in enumerate(channel_commands):
                    cmd_name = cmd.get("name", "")
                    cmd_main = cmd_name.split()[0] if cmd_name else ""
                    cmd_bot_id = cmd.get("bot_id")
                    cmd_type = cmd.get("command_type")
                    
                    if (cmd_main == command_name and 
                        str(cmd_bot_id) == str(bot_id) and 
                        cmd_type == "slash"):
                        current_execution_type = cmd.get("execution_type")
                        if current_execution_type != execution_type:
                            cmd["execution_type"] = execution_type
                            ccr_log_to_file(f"Updated execution_type for command '{cmd_name}' (main: '{command_name}') -> {execution_type}", level="SUCCESS", debug_mode=debug_mode)
                        else:
                            ccr_log_to_file(f"Execution_type for command '{cmd_name}' already set to {execution_type}, no update needed", debug_mode=debug_mode)
                        break
                else:
                    ccr_log_to_file(f"Command '{command_name}' with bot_id {bot_id} not found in channel {channel_id} for execution_type update", debug_mode=debug_mode)
                await ccr_save_json_data(CCR_CHANNELS_FILE, channels_cfg)
        except Exception as e:
            ccr_log_to_file(f"Error saving execution_type to config: {e}", debug_mode=debug_mode)
    
    async def ccr_fetch_global_command(bot_id, command_name, debug_mode=False):
        """Fetch a specific global command for a bot"""
        try:
            headers = {
                "Authorization": bot.http.token,
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            # Fetch global commands for the application
            async with aiohttp.ClientSession() as session:
                url = f"https://discord.com/api/v9/applications/{bot_id}/commands"
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        global_commands = await resp.json()
                        available_commands = [cmd.get('name', 'unknown') for cmd in global_commands]
                        ccr_log_to_file(f"Available global commands for bot {bot_id}: {available_commands}", debug_mode=debug_mode)
                        
                        # Find the command we're looking for
                        for cmd in global_commands:
                            if cmd.get('name') == command_name:
                                class MockSlashCmd:
                                    def __init__(self, cmd_data):
                                        self.id = cmd_data['id']
                                        self.version = cmd_data['version']
                                        self.description = cmd_data.get('description', '')
                                        self.options = cmd_data.get('options', [])
                                        self.name = cmd_data.get('name', '')
                                        self.type = cmd_data.get('type', 1)
                                
                                option_count = len(cmd.get('options', []))
                                ccr_log_to_file(f"Found global command '{command_name}' for bot {bot_id} ({option_count} options available)", debug_mode=debug_mode)
                                return MockSlashCmd(cmd)
                        
                        if debug_mode:
                            ccr_log_to_file(f"Command '{command_name}' not found in global commands. Available commands: {available_commands}", debug_mode=debug_mode)
                                
        except Exception as e:
            ccr_log_to_file(f"Error fetching global commands: {e}", debug_mode=debug_mode)
        
        return None

    def ccr_safe_int(value, default=0):
        try:
            return int(str(value).strip())
        except (ValueError, TypeError, AttributeError):
            return default

    def ccr_get_default_state():
        return {
            "is_running": False, "webhook_url": None,
            "console_logs_enabled": False, "last_used": {},
            "debug_mode": False, 
            "reuse_bot_names": True
        }

    # --- Custom Slash Command Execution Function ---
    def ccr_log_to_file(message, level="INFO", debug_mode=None, important=False):
        """Log messages to file with different levels of detail
        Args:
            message: Log message
            level: Log level (INFO, ERROR, SUCCESS, etc.)
            debug_mode: Debug mode state (auto-loaded if None)
            important: If True, always log regardless of debug_mode
        """
        # Load debug_mode from state if not explicitly provided
        if debug_mode is None:
            try:
                # Load state data
                state_file = CCR_STATE_FILE
                if state_file.exists():
                    with state_file.open("r", encoding="utf-8") as f:
                        state_data = json.load(f)
                    debug_mode = state_data.get('debug_mode', False)
                else:
                    debug_mode = False
            except:
                debug_mode = False
    
        if not important and debug_mode is False:
            return
            
        log_dir = os.path.join(getScriptsPath(), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "ccr.log")
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] [{level}] {message}\n")
        except Exception as e:
            print(f"Error writing to log file: {e}")
    
    def ccr_convert_options_to_dict(options):
        """Convert Option objects to dictionaries for JSON serialization"""
        if not options:
            return []
        
        result = []
        for option in options:
            if hasattr(option, 'name'):
                option_dict = {
                    'name': option.name,
                    'type': option.type,
                    'description': getattr(option, 'description', ''),
                    'required': getattr(option, 'required', False)
                }
                if hasattr(option, 'options') and option.options:
                    option_dict['options'] = ccr_convert_options_to_dict(option.options)
                result.append(option_dict)
            else:
                result.append(option)
        
        return result

    async def execute_slash_command_custom(channel, bot_id, command_name, debug_mode=False, **kwargs):
        """
        Custom implementation to execute slash commands with proper argument handling.
        Supports both server bots and user-accessible application bots.
        Handles subcommands (e.g., 'help 2' -> command='help', subcommand='2')
        Uses caching in ccr_channels.json to improve performance by storing command type (server/global)
        Args:
            channel: Discord channel object
            bot_id: Target bot ID
            command_name: Name of the slash command (can include subcommands)
            debug_mode: Whether to enable debug logging
            **kwargs: Command arguments as key-value pairs
        Returns:
            dict: {"success": bool, "status_code": int, "response": dict}
        """
        ccr_log_to_file(f"🚀 Starting execution of command: {command_name}", debug_mode=debug_mode, important=True)
        
        start_time = time.time() if debug_mode else None
        fetch_start_time = None
        fetch_end_time = None
        execute_start_time = None
        execution_type = None
        
        try:
            # Parse command name to handle subcommands
            command_parts = command_name.strip().split()
            main_command = command_parts[0] if command_parts else command_name
            subcommand = command_parts[1] if len(command_parts) > 1 else None
            subcommand_group = command_parts[2] if len(command_parts) > 2 else None
            
            ccr_log_to_file(f"Parsing command '{command_name}' -> main: '{main_command}', sub: '{subcommand}', group: '{subcommand_group}'", debug_mode=debug_mode)
            
            # Load channels config to check if we already know the command type
            channels_cfg = await ccr_load_json_data(CCR_CHANNELS_FILE, {"channels": {}})
            channel_id = str(channel.id)
            cached_slash_type = None
            
            # Find the command in the channel config and get its cached slash_type and execution_type
            if channel_id in channels_cfg.get("channels", {}):
                channel_commands = channels_cfg["channels"][channel_id].get("commands", [])
                for cmd in channel_commands:
                    cmd_name = cmd.get("name", "")
                    cmd_main = cmd_name.split()[0] if cmd_name else ""
                    
                    if (cmd_main == main_command and 
                        ccr_safe_int(cmd.get("bot_id", 0)) == ccr_safe_int(bot_id) and 
                        cmd.get("command_type") == "slash"):
                        cached_slash_type = cmd.get("slash_type")
                        execution_type = cmd.get("execution_type", "direct")  # Default to "direct" if not set
                        break
            
            slash_cmd = None
            command_type = None  # 'server' or 'global'
            
            # Start timing for fetch operation
            if debug_mode:
                fetch_start_time = time.time()
                ccr_log_to_file(f"⏱️ Starting fetch operation for command '{main_command}'", debug_mode=debug_mode)
            
            # If we have cached slash_type, try the cached type first
            if cached_slash_type:
                ccr_log_to_file(f"Found cached slash_type for '{main_command}': {cached_slash_type}", debug_mode=debug_mode)
                
                if cached_slash_type == 'server':
                    slash_cmd = await fetchSlashCommand(channel, bot_id, main_command)

                    if slash_cmd:
                        command_type = 'server'
                        ccr_log_to_file(f"✅ Found command '{main_command}' in server for bot {bot_id} (from cache)", debug_mode=debug_mode)
                elif cached_slash_type == 'global':
                    # Try global commands directly
                    slash_cmd = await ccr_fetch_global_command(bot_id, main_command, debug_mode)
                    if slash_cmd:
                        command_type = 'global'
                        ccr_log_to_file(f"✅ Found command '{main_command}' as global for bot {bot_id} (from cache)", debug_mode=debug_mode)
            
            # If cache miss or cached command not found, do full search
            if not slash_cmd:
                ccr_log_to_file(f"Cache miss or cached command not found, performing full search for '{main_command}'", debug_mode=debug_mode)
                
                # Step 1: Try to fetch the slash command from server first
                slash_cmd = await fetchSlashCommand(channel, bot_id, main_command)
                
                if slash_cmd:
                    command_type = 'server'
                    ccr_log_to_file(f"✅ Found command '{main_command}' in server for bot {bot_id}", debug_mode=debug_mode)
                
                # If not found in server, try to get it from global application commands
                if not slash_cmd:
                    ccr_log_to_file(f"Command '{main_command}' not found in server for bot {bot_id}, trying global commands...", debug_mode=debug_mode)
                    slash_cmd = await ccr_fetch_global_command(bot_id, main_command, debug_mode)
                    if slash_cmd:
                        command_type = 'global'
                
                if slash_cmd and command_type and channel_id in channels_cfg.get("channels", {}):
                    await ccr_save_slash_type_to_config(channel_id, main_command, bot_id, command_type, debug_mode)
            
            # End timing for fetch operation
            if debug_mode and fetch_start_time:
                fetch_end_time = time.time()
                fetch_duration = fetch_end_time - fetch_start_time
                ccr_log_to_file(f"⏱️ Fetch operation completed in {fetch_duration:.3f}s for command '{main_command}' (type: {command_type or 'not found'})", debug_mode=debug_mode)
            
            if not slash_cmd:
                error_msg = f"❌ Slash command '{main_command}' not found for bot {bot_id} (tried both server and global commands)"
                
                ccr_log_to_file(error_msg, level="ERROR", debug_mode=debug_mode, important=True)
                
                # Auto-disable the command
                disable_result = await ccr_disable_command_automatically(channel.id, main_command, bot_id, debug_mode)
                
                return {"success": False, "status_code": 404, "response": {"error": error_msg}}
            
            payload = {
                "type": 2,
                "application_id": str(bot_id),
                "channel_id": str(channel.id),
                "session_id": "placeholder_session",
                "nonce": str(int(time.time() * 1000)),
                "data": {
                    "version": str(getattr(slash_cmd, 'version', '1')),
                    "id": str(slash_cmd.id),
                    "name": main_command,
                    "type": 1,
                    "options": []
                }
            }
            
            if hasattr(channel, 'guild') and channel.guild:
                payload["guild_id"] = str(channel.guild.id)
            
            ccr_log_to_file(f"Built payload for command '{main_command}' with bot {bot_id}", debug_mode=debug_mode)
            guild_info = getattr(channel.guild, 'id', 'DM') if hasattr(channel, 'guild') and channel.guild else 'DM'
            ccr_log_to_file(f"Channel: {channel.id}, Guild: {guild_info}", debug_mode=debug_mode)
            
            # Step 3: Handle subcommands, subcommand groups, and arguments
            if subcommand:
                if subcommand_group:
                    # Handle 3-level command:
                    subcommand_group_option = {
                        "type": 2,  # SUB_COMMAND_GROUP
                        "name": subcommand,  # the subcommand group
                        "options": []
                    }
                    
                    # Second level: actual subcommand
                    actual_subcommand_option = {
                        "type": 1,  # SUB_COMMAND
                        "name": subcommand_group,  # the actual subcommand
                        "options": []
                    }
                    
                    # Check command structure regardless of kwargs
                    command_options = getattr(slash_cmd, 'options', [])
                    subcommand_group_def = None
                    actual_subcommand_def = None
                    
                    # Find the subcommand group definition
                    ccr_log_to_file(f"DEBUG: Looking for subcommand_group '{subcommand}' in {len(command_options)} options", important=True)
                    for cmd_option in command_options:
                        cmd_name = cmd_option.name if hasattr(cmd_option, 'name') else cmd_option.get('name')
                        cmd_type = cmd_option.type if hasattr(cmd_option, 'type') else cmd_option.get('type')
                        ccr_log_to_file(f"DEBUG: Found option '{cmd_name}' with type {cmd_type}", important=True)
                        if cmd_name == subcommand and cmd_type == 2:  # SUB_COMMAND_GROUP
                            subcommand_group_def = cmd_option
                            ccr_log_to_file(f"DEBUG: Found subcommand_group_def for '{subcommand}'", important=True)
                            break
                    
                    # Find the actual subcommand definition within the group
                    if subcommand_group_def:
                        group_options = getattr(subcommand_group_def, 'options', []) if hasattr(subcommand_group_def, 'options') else subcommand_group_def.get('options', [])
                        ccr_log_to_file(f"DEBUG: Looking for subcommand '{subcommand_group}' in {len(group_options)} group options", important=True)
                        for group_option in group_options:
                            group_opt_name = group_option.name if hasattr(group_option, 'name') else group_option.get('name')
                            group_opt_type = group_option.type if hasattr(group_option, 'type') else group_option.get('type')
                            ccr_log_to_file(f"DEBUG: Found group option '{group_opt_name}' with type {group_opt_type}", important=True)
                            if group_opt_name == subcommand_group and group_opt_type == 1:  # SUB_COMMAND
                                actual_subcommand_def = group_option
                                ccr_log_to_file(f"DEBUG: Found actual_subcommand_def for '{subcommand_group}'", important=True)
                                break
                    else:
                        ccr_log_to_file(f"DEBUG: subcommand_group_def not found for '{subcommand}'", important=True)
                    
                    # If there are kwargs, add them to the actual subcommand options
                    if kwargs:
                        
                        # Add arguments to the actual subcommand
                        for key, value in kwargs.items():
                            actual_param_name = key
                            if main_command == '8ball' and key == 'pregunta':
                                actual_param_name = 'question'
                            
                            option_def = None
                            sub_options = getattr(actual_subcommand_def, 'options', []) if actual_subcommand_def else []
                            if not sub_options and actual_subcommand_def and hasattr(actual_subcommand_def, '__getitem__'):
                                sub_options = actual_subcommand_def.get('options', [])
                            
                            for sub_option in sub_options:
                                sub_name = sub_option.name if hasattr(sub_option, 'name') else sub_option.get('name')
                                if sub_name == actual_param_name:
                                    option_def = sub_option
                                    break
                            
                            # Handle choices and option types
                            final_value = str(value)
                            if option_def:
                                choices = getattr(option_def, 'choices', []) if hasattr(option_def, 'choices') else option_def.get('choices', [])
                                if choices:
                                    for choice in choices:
                                        choice_name = choice.get('name', '') if isinstance(choice, dict) else getattr(choice, 'name', '')
                                        choice_value = choice.get('value', '') if isinstance(choice, dict) else getattr(choice, 'value', '')
                                        if str(value) == choice_name or str(value) == choice_value:
                                            final_value = choice_value
                                            break
                            
                            # Get the correct option type
                            option_type = 3  # STRING type by default
                            if option_def:
                                if hasattr(option_def, 'type'):
                                    option_type = option_def.type.value if hasattr(option_def.type, 'value') else option_def.type
                                else:
                                    option_type = option_def.get('type', 3)
                            
                            # Create the option based on type
                            if option_type == 6:  # USER type
                                option = {
                                    "type": option_type,
                                    "name": actual_param_name,
                                    "value": str(final_value)
                                }
                            elif option_type == 9:  # MENTIONABLE type
                                option = {
                                    "type": option_type,
                                    "name": actual_param_name,
                                    "value": str(final_value)
                                }
                            elif option_type == 4:  # INTEGER type
                                try:
                                    if '.' in str(final_value):
                                        try:
                                            float_val = float(str(final_value))
                                            int_value = int(float_val)
                                        except (ValueError, TypeError):
                                            raise ValueError(f"Cannot convert '{final_value}' to integer")
                                    else:
                                        int_value = int(final_value)
                                    option = {
                                        "type": option_type,
                                        "name": actual_param_name,
                                        "value": int_value
                                    }
                                except ValueError:
                                    option = {
                                        "type": 3,  # Fallback to STRING
                                        "name": actual_param_name,
                                        "value": str(final_value)
                                    }
                            elif option_type == 5:  # BOOLEAN type
                                bool_value = str(final_value).lower() in ['true', '1', 'yes', 'on']
                                option = {
                                    "type": option_type,
                                    "name": actual_param_name,
                                    "value": bool_value
                                }
                            else:  # STRING and other types
                                option = {
                                    "type": option_type,
                                    "name": actual_param_name,
                                    "value": str(final_value)
                                }
                            
                            actual_subcommand_option["options"].append(option)
                    
                    # Add the actual subcommand to the subcommand group
                    subcommand_group_option["options"].append(actual_subcommand_option)
                    
                    # Add the subcommand group to the main payload
                    payload["data"]["options"].append(subcommand_group_option)
                    ccr_log_to_file(f"Added 3-level command structure: '{main_command}' -> '{subcommand}' -> '{subcommand_group}' with {len(kwargs)} arguments", debug_mode=debug_mode)
                    
                else:
                    # Handle 2-level command: /command subcommand
                    subcommand_option = {
                        "type": 1,  # SUB_COMMAND
                        "name": subcommand,
                        "options": []
                    }
                    
                    # If there are kwargs, add them to the subcommand options
                    if kwargs:
                        command_options = getattr(slash_cmd, 'options', [])
                        subcommand_def = None
                        for cmd_option in command_options:
                            # Handle both dict and Option object
                            cmd_name = cmd_option.name if hasattr(cmd_option, 'name') else cmd_option.get('name')
                            cmd_type = cmd_option.type if hasattr(cmd_option, 'type') else cmd_option.get('type')
                            if cmd_name == subcommand and cmd_type == 1:
                                subcommand_def = cmd_option
                                break
                    
                    for key, value in kwargs.items():
                        # Handle parameter name mapping for specific commands
                        actual_param_name = key
                        if main_command == '8ball' and key == 'pregunta':
                            actual_param_name = 'question'
                        
                        option_def = None
                        sub_options = getattr(subcommand_def, 'options', []) if subcommand_def else []
                        if not sub_options and subcommand_def and hasattr(subcommand_def, '__getitem__'):
                            sub_options = subcommand_def.get('options', [])
                        
                        for sub_option in sub_options:
                            sub_name = sub_option.name if hasattr(sub_option, 'name') else sub_option.get('name')
                            if sub_name == actual_param_name:
                                option_def = sub_option
                                break
                        
                        # Handle choices - if the option has choices, find the correct value
                        final_value = str(value)
                        if option_def:
                            choices = getattr(option_def, 'choices', []) if hasattr(option_def, 'choices') else option_def.get('choices', [])
                            if choices:
                                # Look for the choice that matches the provided value (either by name or value)
                                for choice in choices:
                                    choice_name = choice.get('name', '') if isinstance(choice, dict) else getattr(choice, 'name', '')
                                    choice_value = choice.get('value', '') if isinstance(choice, dict) else getattr(choice, 'value', '')
                                    if str(value) == choice_name or str(value) == choice_value:
                                        final_value = choice_value
                                        break
                        
                        # Get the correct option type from subcommand definition
                        option_type = 3  # STRING type by default
                        if option_def:
                            if hasattr(option_def, 'type'):
                                option_type = option_def.type.value if hasattr(option_def.type, 'value') else option_def.type
                            else:
                                option_type = option_def.get('type', 3)
                        
                        # Handle different argument types properly for subcommands
                        if option_type == 6:  # USER type
                            option = {
                                "type": option_type,
                                "name": actual_param_name,
                                "value": str(final_value)
                            }
                            ccr_log_to_file(f"Processing USER subcommand argument '{actual_param_name}': {final_value}", debug_mode=debug_mode)
                        elif option_type == 9:  # MENTIONABLE type
                            option = {
                                "type": option_type,
                                "name": actual_param_name,
                                "value": str(final_value)
                            }
                            ccr_log_to_file(f"Processing MENTIONABLE subcommand argument '{actual_param_name}': {final_value}", debug_mode=debug_mode)
                        elif option_type == 4:  # INTEGER type
                            try:
                                if '.' in str(final_value):
                                    try:
                                        float_val = float(str(final_value))
                                        int_value = int(float_val)
                                    except (ValueError, TypeError):
                                        raise ValueError(f"Cannot convert '{final_value}' to integer")
                                else:
                                    int_value = int(final_value)
                                option = {
                                    "type": option_type,
                                    "name": actual_param_name,
                                    "value": int_value
                                }
                            except ValueError:
                                option = {
                                    "type": 3,  # Fallback to STRING
                                    "name": actual_param_name,
                                    "value": str(final_value)
                                }
                        elif option_type == 5:  # BOOLEAN type
                            bool_value = str(final_value).lower() in ['true', '1', 'yes', 'on']
                            option = {
                                "type": option_type,
                                "name": actual_param_name,
                                "value": bool_value
                            }
                        else:  # STRING and other types
                            option = {
                                "type": option_type,
                                "name": actual_param_name,
                                "value": str(final_value)
                            }
                        
                        subcommand_option["options"].append(option)
                    
                    payload["data"]["options"].append(subcommand_option)
                    ccr_log_to_file(f"Added subcommand '{subcommand}' with {len(kwargs)} arguments", debug_mode=debug_mode)
                
            elif kwargs:
                # No subcommand, add arguments directly to main command
                command_options = getattr(slash_cmd, 'options', [])
                
                for key, value in kwargs.items():
                    actual_param_name = key
                    if main_command == '8ball' and key == 'pregunta':
                        actual_param_name = 'question'
                    
                    # Find the option definition for choices handling only
                    option_def = None
                    for cmd_option in command_options:
                        # Handle both dict and Option object
                        cmd_name = cmd_option.name if hasattr(cmd_option, 'name') else cmd_option.get('name')
                        if cmd_name == actual_param_name:
                            option_def = cmd_option
                            break
                    
                    # Handle choices - if the option has choices, find the correct value
                    clean_value = str(value).strip('"\'')
                    final_value = clean_value
                    if option_def:
                        choices = getattr(option_def, 'choices', []) if hasattr(option_def, 'choices') else option_def.get('choices', [])
                        if choices:
                            for choice in choices:
                                choice_name = choice.get('name', '') if isinstance(choice, dict) else getattr(choice, 'name', '')
                                choice_value = choice.get('value', '') if isinstance(choice, dict) else getattr(choice, 'value', '')
                                if clean_value == choice_name or clean_value == choice_value:
                                    final_value = choice_value
                                    break
                    
                    # Get the correct option type from command definition
                    option_type = 3  # STRING type by default
                    if option_def:
                        if hasattr(option_def, 'type'):
                            option_type = option_def.type.value if hasattr(option_def.type, 'value') else option_def.type
                        else:
                            option_type = option_def.get('type', 3)

                    
                    # Handle different argument types properly
                    if option_type == 6:  # USER type
                        option = {
                            "type": option_type,
                            "name": actual_param_name,
                            "value": str(final_value)
                        }
                        ccr_log_to_file(f"Processing USER argument '{actual_param_name}': {final_value}", debug_mode=debug_mode)
                    elif option_type == 9:  # MENTIONABLE type
                        option = {
                            "type": option_type,
                            "name": actual_param_name,
                            "value": str(final_value)
                        }
                        ccr_log_to_file(f"Processing MENTIONABLE argument '{actual_param_name}': {final_value}", debug_mode=debug_mode)
                    elif option_type == 4:  # INTEGER type
                        try:
                            option = {
                                "type": option_type,
                                "name": actual_param_name,
                                "value": int(final_value)
                            }
                        except ValueError:
                            option = {
                                "type": 3,  # Fallback to STRING
                                "name": actual_param_name,
                                "value": str(final_value)
                            }
                    elif option_type == 10:  # NUMBER type
                        try:
                            option = {
                                "type": option_type,
                                "name": actual_param_name,
                                "value": float(final_value)
                            }
                        except ValueError:
                            option = {
                                "type": 3,  # Fallback to STRING
                                "name": actual_param_name,
                                "value": str(final_value)
                            }
                    elif option_type == 5:  # BOOLEAN type
                        option = {
                            "type": option_type,
                            "name": actual_param_name,
                            "value": str(final_value).lower() in ('true', '1', 'yes', 'on')
                        }
                    else:  # STRING and other types
                        option = {
                            "type": option_type,
                            "name": actual_param_name,
                            "value": str(final_value)
                        }
                    payload["data"]["options"].append(option)
                    
            
            # Handle commands without subcommands
            if not subcommand:
                
                # Check if command is marked as API-only
                if execution_type == "api":
                    ccr_log_to_file(f"Skipping direct execution for /{main_command} (marked as API-only)", debug_mode=debug_mode)
                elif not kwargs:
                    # Command has no subcommands and no arguments - execute directly
                    ccr_log_to_file(f"Executing command '{main_command}' directly without subcommands or arguments", debug_mode=debug_mode)
                    
                    # Start timing for execute operation
                    if debug_mode:
                        execute_start_time = time.time()
                        ccr_log_to_file(f"⏱️ Starting execute operation for command '{main_command}'", debug_mode=debug_mode)
                    
                    try:
                        result = await slash_cmd(channel)
                        
                        # Log timing for successful execution
                        if debug_mode:
                            execute_end_time = time.time()
                            execute_duration = execute_end_time - execute_start_time
                            ccr_log_to_file(f"⏱️ Execute operation completed in {execute_duration:.3f} seconds", debug_mode=debug_mode)
                        
                        # Log total operation time
                        if debug_mode and start_time is not None:
                            total_end_time = time.time()
                            total_duration = total_end_time - start_time
                            fetch_duration = fetch_end_time - fetch_start_time if 'fetch_end_time' in locals() and 'fetch_start_time' in locals() and fetch_start_time is not None and fetch_end_time is not None else 0
                            ccr_log_to_file(f"⏱️ Total operation time: {total_duration:.3f}s (Fetch: {fetch_duration:.3f}s, Execute: {execute_duration:.3f}s)", debug_mode=debug_mode, important=True)
                        
                        # Save successful direct execution type
                        if execution_type != "direct":
                            await ccr_save_execution_type_to_config(str(channel.id), main_command, bot_id, "direct", debug_mode)
                        ccr_log_to_file(f"✅ Successfully executed /{main_command} directly in channel {channel.id}" + "\n", level="SUCCESS", debug_mode=debug_mode, important=True)
                        return {"success": True, "status_code": 200, "response": {}}
                    except Exception as direct_exec_error:
                        error_msg = str(direct_exec_error)
                        ccr_log_to_file(f"❌ Direct execution failed for /{main_command}: {error_msg}", level="ERROR", debug_mode=debug_mode)
                        # Save as API-only if it's a MockSlashCmd error
                        if "'MockSlashCmd' object is not callable" in error_msg:
                            await ccr_save_execution_type_to_config(str(channel.id), main_command, bot_id, "api", debug_mode)
                            ccr_log_to_file(f"📝 Marked /{main_command} as API-only due to MockSlashCmd error", debug_mode=debug_mode)
                        # Fall back to API method below
                elif execution_type != "api":
                    # Command has arguments but no subcommands - execute with args (only if not marked as API-only)
                    ccr_log_to_file(f"Executing command '{main_command}' directly with arguments: {kwargs}", debug_mode=debug_mode)
                    
                    # Start timing for execute operation
                    if debug_mode:
                        execute_start_time = time.time()
                        ccr_log_to_file(f"⏱️ Starting execute operation for command '{main_command}'", debug_mode=debug_mode)
                    
                    try:
                        result = await slash_cmd(channel, **kwargs)
                        
                        # Log timing for successful execution
                        if debug_mode:
                            execute_end_time = time.time()
                            execute_duration = execute_end_time - execute_start_time
                            ccr_log_to_file(f"⏱️ Execute operation completed in {execute_duration:.3f} seconds", debug_mode=debug_mode)
                        
                        # Log total operation time
                        if debug_mode and start_time is not None:
                            total_end_time = time.time()
                            total_duration = total_end_time - start_time
                            fetch_duration = fetch_end_time - fetch_start_time if 'fetch_end_time' in locals() and 'fetch_start_time' in locals() and fetch_start_time is not None and fetch_end_time is not None else 0
                            ccr_log_to_file(f"⏱️ Total operation time: {total_duration:.3f}s (Fetch: {fetch_duration:.3f}s, Execute: {execute_duration:.3f}s)", debug_mode=debug_mode, important=True)
                        
                        # Save successful direct execution type
                        if execution_type != "direct":
                            await ccr_save_execution_type_to_config(str(channel.id), main_command, bot_id, "direct", debug_mode)
                        ccr_log_to_file(f"✅ Successfully executed /{main_command} with args directly in channel {channel.id}" + "\n", level="SUCCESS", debug_mode=debug_mode, important=True)
                        return {"success": True, "status_code": 200, "response": {}}
                    except Exception as direct_exec_error:
                        error_msg = str(direct_exec_error)
                        ccr_log_to_file(f"❌ Direct execution with args failed for /{main_command}: {error_msg}", level="ERROR", debug_mode=debug_mode)
                        # Save as API-only if it's a MockSlashCmd error
                        if "'MockSlashCmd' object is not callable" in error_msg:
                            await ccr_save_execution_type_to_config(str(channel.id), main_command, bot_id, "api", debug_mode)
                            ccr_log_to_file(f"📝 Marked /{main_command} as API-only", debug_mode=debug_mode)
                    
            # Step 4: Send the interaction via Discord API (fallback method)
            url = "https://discord.com/api/v10/interactions"
            
            # Get the token
            token = bot.http.token
            if token.startswith('Bot '):
                token = token[4:]
            
            headers = {
                "Authorization": token,
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            ccr_log_to_file(f"Executing /{command_name} in channel {channel.id} with args: {kwargs}", debug_mode=debug_mode, important=True)
            
            # Start timing for execute operation
            if debug_mode:
                execute_start_time = time.time()
                ccr_log_to_file(f"⏱️ Starting execute operation for command '{command_name}'", debug_mode=debug_mode)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    response_text = await response.text()
                    
                    if response.status == 204:
                        # Log timing for successful execution
                        if debug_mode:
                            execute_end_time = time.time()
                            execute_duration = execute_end_time - execute_start_time
                            ccr_log_to_file(f"⏱️ Execute operation completed in {execute_duration:.3f} seconds", debug_mode=debug_mode)
                        
                        # Log total operation time
                        if debug_mode and start_time is not None:
                            total_end_time = time.time()
                            total_duration = total_end_time - start_time
                            fetch_duration = fetch_end_time - fetch_start_time if 'fetch_end_time' in locals() and 'fetch_start_time' in locals() and fetch_start_time is not None and fetch_end_time is not None else 0
                            ccr_log_to_file(f"⏱️ Total operation time: {total_duration:.3f}s (Fetch: {fetch_duration:.3f}s, Execute: {execute_duration:.3f}s)", debug_mode=debug_mode, important=True)
                        
                        # Save successful API execution type (only if different)
                        if execution_type != "api":
                            await ccr_save_execution_type_to_config(str(channel.id), command_name, bot_id, "api", debug_mode)
                        ccr_log_to_file(f"✅ Successfully executed /{command_name} in channel {channel.id}" + "\n", level="SUCCESS", debug_mode=debug_mode, important=True)
                        return {"success": True, "status_code": response.status, "response": {}}
                    else:
                        # Log timing for failed execution
                        if debug_mode:
                            execute_end_time = time.time()
                            execute_duration = execute_end_time - execute_start_time
                            ccr_log_to_file(f"⏱️ Execute operation failed after {execute_duration:.3f} seconds", debug_mode=debug_mode, important=True)

                        ccr_log_to_file(f"❌ Failed to execute /{command_name}. Status: {response.status}", level="ERROR", debug_mode=debug_mode, important=True)
                        ccr_log_to_file(f"Response: {response_text}", debug_mode=debug_mode)
                        
                        # Log total operation time for failed execution
                        if debug_mode and start_time is not None:
                            total_end_time = time.time()
                            total_duration = total_end_time - start_time
                            fetch_duration = fetch_end_time - fetch_start_time if 'fetch_end_time' in locals() and 'fetch_start_time' in locals() and fetch_start_time is not None and fetch_end_time is not None else 0
                            ccr_log_to_file(f"⏱️ Total operation time (failed): {total_duration:.3f}s (Fetch: {fetch_duration:.3f}s, Execute: {execute_duration:.3f}s)", debug_mode=debug_mode, important=True)
                            ccr_log_to_file(" " * 60 + "\n", debug_mode=debug_mode)

                        try:
                            response_json = await response.json()
                        except:
                            response_json = {"error": response_text}
                        return {"success": False, "status_code": response.status, "response": response_json}
                        
        except Exception as e:
            # Log timing for exception
            if debug_mode:
                if 'execute_start_time' in locals() and execute_start_time is not None:
                    execute_end_time = time.time()
                    execute_duration = execute_end_time - execute_start_time
                    ccr_log_to_file(f"⏱️ Execute operation failed with exception after {execute_duration:.3f} seconds", debug_mode=debug_mode)
                
                # Log total operation time for exception
                if start_time is not None:
                    total_end_time = time.time()
                    total_duration = total_end_time - start_time
                    fetch_duration = fetch_end_time - fetch_start_time if 'fetch_end_time' in locals() and 'fetch_start_time' in locals() and fetch_start_time is not None and fetch_end_time is not None else 0
                    execute_duration = execute_duration if 'execute_duration' in locals() else 0
                    ccr_log_to_file(f"⏱️ Total operation time (exception): {total_duration:.3f}s (Fetch: {fetch_duration:.3f}s, Execute: {execute_duration:.3f}s)", debug_mode=debug_mode)
                ccr_log_to_file(" " * 60 + "\n", debug_mode=debug_mode)
            
            ccr_log_to_file(f"Error in custom slash execution: {str(e)}", level="ERROR", debug_mode=debug_mode, important=True)
            traceback.print_exc()
            return {"success": False, "status_code": 0, "response": {"error": f"Exception: {str(e)}"}}

    # --- Main Manager Class ---
    class CommandRunnerManager:
        def __init__(self):
            self.running = False
            self.scheduler_task = None
            self.cleanup_task = None
            self.ui_updater = None
            self.channel_editor_updater = None
            self.ui_state = {}
            self.reschedule_event = asyncio.Event()
            self.command_locks = {}
            self.channels_cfg = {"channels": {}}
            self.state = {}
            self.ui_elements = None
            self.pending_slash_responses = {}
            self.slash_command_results = {}
            self.pending_responses_lock = asyncio.Lock()
            self.state_lock = asyncio.Lock()

        async def ccr_load_initial_data(self):
            self.channels_cfg = await ccr_load_json_data(CCR_CHANNELS_FILE, {"channels": {}})
            self.state = await ccr_load_json_data(CCR_STATE_FILE, ccr_get_default_state())

        def ccr_set_ui_elements(self, ui_elements):
            self.ui_elements = ui_elements

        def ccr_ensure_dynamic_slots(self, needed_slots, ccr_manager_ref=None):
            """Ensure we have enough command slots for the given number of commands"""
            current_slots = len(self.ui_elements.get("command_slots", []))
            command_control_group = self.ui_elements.get("command_control_group")
            
            if not command_control_group:
                return
            
            # Create additional slots if needed
            while current_slots < needed_slots:
                row = command_control_group.create_group(type="rows", gap=0, full_width=True, visible=False)
                first_row = row.create_group(type="columns", gap=8, align_items="center", full_width=True)
                toggle = first_row.create_ui_element(UI.Toggle, label=" ", checked=True, visible=False)
                
                self.ui_elements["command_slots"].append({"group": row, "toggle": toggle})
                current_slots += 1

        def ccr_populate_editor(self, config, channel_id=None, ccr_manager_ref=None, ccr_tab=None, ccr_update_command_selector=None):
            channel_obj = bot.get_channel(int(channel_id)) if channel_id else None
            channel_name = f"#{channel_obj.name}" if channel_obj else "Template"
            self.ui_elements["editor_title"].content = f"Editing: {channel_name}{f' ({channel_id})' if channel_id else ''}"
            self.ui_state["selected_channel_id"] = channel_id

            # Set default values for new command fields
            self.ui_elements["new_command_prefix_input"].value = "!"
            self.ui_elements["timer_start_input"].value = ""
            self.ui_elements["timer_end_input"].value = ""
            self.ui_elements["timer_days_select"].selected_items = []
            
            humanization = config.get("humanization", {})
            self.ui_elements["typing_toggle"].checked = humanization.get("typing", True)
            human_delay = humanization.get("human_delay", {})
            self.ui_elements["human_delay_toggle"].checked = human_delay.get("enabled", True)
            self.ui_elements["min_delay_input"].value = str(human_delay.get("min", 5))
            self.ui_elements["max_delay_input"].value = str(human_delay.get("max", 45))
            
            custom_commands = config.get("commands", [])
            needed_slots = len(custom_commands) + 1
            self.ccr_ensure_dynamic_slots(needed_slots, ccr_manager_ref)
            
            command_slots = self.ui_elements.get("command_slots", [])
            self.ui_elements["no_commands_text"].visible = not custom_commands
            
            gap_value = 4 if custom_commands else 0
            for slot in command_slots:
                slot["group"].gap = gap_value

            for i, slot in enumerate(command_slots):
                if i < len(custom_commands):
                    cmd = custom_commands[i]
                    slot["group"].visible = True
                    
                    # Store original command name for saving
                    cmd_name = cmd.get("name", "")
                    slot["original_name"] = cmd_name
                    
                    # Format command name with type prefix for display
                    cmd_type = cmd.get("command_type", "prefix")
                    if cmd_type == "slash":
                        base_display_name = f"/{cmd_name}"
                    else:
                        cmd_prefix = cmd.get("prefix", "!")
                        base_display_name = f"{cmd_prefix}{cmd_name}"

                    # Get bot name for display
                    bot_name = cmd.get("bot_name", "")
                    bot_id = cmd.get("bot_id", "")
                    bot_display = bot_name if bot_name else str(bot_id)

                    # Combine command name and bot display
                    display_name = f"{base_display_name} ({bot_display})"
                    
                    safe_display_name = str(display_name).replace('"', '\"').replace("'", "\\'")
                    slot["toggle"].label = safe_display_name
                    slot["toggle"].checked = cmd.get("enabled", True)
                    slot["toggle"].visible = True
                else:
                    slot["group"].visible = False
                    slot["original_name"] = ""
                    slot["toggle"].visible = False

        async def ccr_connect_and_populate_ui(self):
            if not self.ui_elements: return

            def update_channel_quick_select():
                channels = self.channels_cfg.get("channels", {})
                channel_options = [{"id": cid, "title": f"#{bot.get_channel(int(cid)).name if bot.get_channel(int(cid)) else '...'} ({cid})"} for cid in channels]
                self.ui_elements["channel_quick_select"].items = channel_options or [{'id': 'no_channels', 'title': 'No channels configured', 'disabled': True}]
                
                # Preserve current selection if it still exists in the channel list
                current_selected = self.ui_state.get("selected_channel_id")
                if current_selected and any(item['id'] == current_selected for item in channel_options):
                    self.ui_elements["channel_quick_select"].selected_items = [current_selected]
                elif not any(item['id'] == current_selected for item in channel_options):
                    self.ui_elements["channel_quick_select"].selected_items = []
                    self.ui_state["selected_channel_id"] = None
            
            # Safety check: ensure state is properly initialized
            async with self.state_lock:
                if not self.state or not isinstance(self.state, dict):
                    self.state = ccr_get_default_state()
                else:
                    # Ensure all required keys exist without overwriting existing values
                    default_state = ccr_get_default_state()
                    for key, default_value in default_state.items():
                        if key not in self.state:
                            self.state[key] = default_value
                
            is_running = self.state.get("is_running", False)
            self.ui_elements["status_text"].content = f"Status: {'RUNNING 🟢' if is_running else 'STOPPED 🔴'}"
            self.ui_elements["master_toggle"].checked = is_running
            self.ui_elements["master_toggle"].disabled = False

            def ccr_update_status_display(is_running):
                if self.ui_elements.get("status_text"):
                    self.ui_elements["status_text"].content = f"Status: {'RUNNING 🟢' if is_running else 'STOPPED 🔴'}"
                if self.ui_elements.get("master_toggle"):
                    self.ui_elements["master_toggle"].checked = is_running
            
            self.ccr_set_ui_updater(ccr_update_status_display)

            self.ui_elements["webhook_input"].value = self.state.get("webhook_url", "")
            self.ui_elements["console_logs_toggle"].checked = self.state.get("console_logs_enabled", False)
            self.ui_elements["reuse_bot_names_toggle"].checked = self.state.get("reuse_bot_names", True)
            update_channel_quick_select()
            self.ui_elements["channel_quick_select"].disabled = False
            self.ui_elements["new_channel_input"].disabled = False
            
            self.ccr_set_channel_editor_updater(update_channel_quick_select)

            # Only reset editor if no channel is currently selected
            current_channel_id = self.ui_state.get("selected_channel_id")
            if current_channel_id and current_channel_id in self.channels_cfg.get("channels", {}):
                # Preserve current channel selection and reload its configuration
                channel_config = self.channels_cfg["channels"][current_channel_id]
                self.ccr_populate_editor(channel_config, channel_id=current_channel_id, ccr_manager_ref=None, ccr_tab=None, ccr_update_command_selector=None)
            else:
                # No valid channel selected, show template
                self.ccr_populate_editor({}, channel_id=None, ccr_manager_ref=None, ccr_tab=None, ccr_update_command_selector=None)
            
            self.ui_elements["editor_card"].visible = True

        def ccr_set_ui_updater(self, updater_func): self.ui_updater = updater_func
        def ccr_set_channel_editor_updater(self, updater_func): self.channel_editor_updater = updater_func

        async def ccr_save_channels(self):
            await ccr_save_json_data(CCR_CHANNELS_FILE, self.channels_cfg)
            if self.channel_editor_updater: self.channel_editor_updater()
        
        async def ccr_remove_channel(self, channel_id):
            if channel_id in self.channels_cfg["channels"]:
                del self.channels_cfg["channels"][channel_id]
                self.command_locks = {k: v for k, v in self.command_locks.items() if not k.startswith(f"{channel_id}-")}
                await self.ccr_save_channels()
        
        async def ccr_remove_custom_command(self, channel_id, command_name):
            if channel_id in self.channels_cfg["channels"]:
                commands = self.channels_cfg["channels"][channel_id].get("commands", [])
                self.channels_cfg["channels"][channel_id]["commands"] = [cmd for cmd in commands if cmd.get("name") != command_name]
                
                # Clean up last_used data for the removed command
                cmd_key = f"{channel_id}-{command_name}"
                if "last_used" in self.state and cmd_key in self.state["last_used"]:
                    del self.state["last_used"][cmd_key]
                    await self.ccr_save_state()
                
                await self.ccr_save_channels()
                self.ccr_trigger_reschedule()

        def _clean_data_for_json(self, data):
            if isinstance(data, dict):
                # Filter out non-serializable objects and manager-specific attributes
                excluded_keys = {'scheduler_task', 'ui_updater', 'channel_editor_updater', 'reschedule_event', 'command_locks', 'ui_elements', 'ui_state'}
                return {k: self._clean_data_for_json(v) for k, v in data.items() 
                       if k not in excluded_keys and not isinstance(v, (asyncio.Task, asyncio.Lock, asyncio.Event, type(lambda: None)))}
            elif isinstance(data, (list, tuple)):
                return [self._clean_data_for_json(item) for item in data 
                       if not isinstance(item, (asyncio.Task, asyncio.Lock, asyncio.Event, type(lambda: None)))]
            elif isinstance(data, (asyncio.Task, asyncio.Lock, asyncio.Event, type(lambda: None))):
                return None 
            else:
                return data

        async def ccr_save_state(self): 
            async with self.state_lock:
                clean_state = self._clean_data_for_json(self.state)
            await ccr_save_json_data(CCR_STATE_FILE, clean_state)

        async def ccr_log(self, title, description, color=0x2f3136, message_obj=None, execution_time=None):
            # Safety check: ensure state is properly initialized
            if not self.state or not isinstance(self.state, dict):
                self.state = ccr_get_default_state()
            else:
                # Ensure all required keys exist without overwriting existing values
                default_state = ccr_get_default_state()
                for key, default_value in default_state.items():
                    if key not in self.state:
                        self.state[key] = default_value
            if not self.state.get("webhook_url") and not self.state.get("console_logs_enabled"): return
            
            # Add execution time to description if debug_mode is enabled and execution_time is provided
            if execution_time is not None and self.state.get("debug_mode", False):
                description += f"\n\n⏱️ **Execution Time**: {execution_time:.3f}s"
            
            if message_obj and hasattr(message_obj, 'jump_url'): description += f"\n\n[Jump to response]({message_obj.jump_url})"
            if self.state.get("webhook_url"):
                try:
                    async with aiohttp.ClientSession() as session:
                        webhook = Webhook.from_url(self.state["webhook_url"], session=session)
                        embed = Embed(title=title, description=description, color=color)
                        embed.set_footer(text=f"CommandRunner v1.2 • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                        await webhook.send(embed=embed, username="CommandRunner Logs")
                except Exception as e: print(f"[CommandRunner] Webhook Error: {e}")
            if self.state.get("console_logs_enabled", False): print(f"[CommandRunner] {title}: {description.splitlines()[0]}")

        async def ccr_start(self):
            if self.running: return
            self.running = True
            self.scheduler_task = bot.loop.create_task(self.ccr_scheduler_loop())
            self.cleanup_task = bot.loop.create_task(self.ccr_cleanup_pending_responses())
            await self.ccr_log("Runner Started", "The command runner task has started.", color=0x57F287)
            if self.ui_updater: self.ui_updater(self.running)
            ccr_log_to_file("🟢 RUNNER STARTED - All scheduled commands have been started" + "\n", debug_mode=True, important=True)

        async def ccr_stop(self):
            if not self.running: return
            self.running = False
            if self.scheduler_task and not self.scheduler_task.done(): self.scheduler_task.cancel()
            if self.cleanup_task and not self.cleanup_task.done(): self.cleanup_task.cancel()
            await self.ccr_log("Runner Stopped", "The command runner task has been stopped.", color=0xED4245)
            ccr_log_to_file("🔴 RUNNER STOPPED - All scheduled commands have been stopped" + "\n", debug_mode=True, important=True)
            if self.ui_updater: self.ui_updater(self.running)

        def parse_slash_arguments(self, args_string):
            """Parse slash command arguments with support for quoted values."""
            kwargs = {}
            
            # First try with quotes around values to handle spaces and special chars
            try:
                quoted_args = []
                parts = args_string.split()
                
                i = 0
                while i < len(parts):
                     part = parts[i]
                     if '=' in part:
                         key, value = part.split('=', 1)
                         
                         # Check if value starts with quote
                         if value.startswith('"'):
                             # Collect until closing quote
                             if value.endswith('"') and len(value) > 1:
                                 quoted_args.append(part)
                             else:
                                 full_value = [value[1:]]  
                                 i += 1
                                 while i < len(parts):
                                     if parts[i].endswith('"'):
                                         full_value.append(parts[i][:-1])  
                                         break
                                     else:
                                         full_value.append(parts[i])
                                     i += 1
                                 quoted_args.append(f'{key}="{" ".join(full_value)}"')
                         else:
                             if any(c in value for c in [' ', '?', '¿', '!', '¡']) or i + 1 < len(parts) and '=' not in parts[i + 1]:
                                 full_value = [value]
                                 i += 1
                                 while i < len(parts) and '=' not in parts[i]:
                                     full_value.append(parts[i])
                                     i += 1
                                 i -= 1 
                                 quoted_args.append(f'{key}="{" ".join(full_value)}"')
                             else:
                                 quoted_args.append(part)
                     else:
                         quoted_args.append(part)
                     i += 1
                
                tokens = shlex.split(' '.join(quoted_args))
                for token in tokens:
                    if '=' in token:
                        key, value = token.split('=', 1)
                        kwargs[key.strip()] = value.strip()
                        
            except (ValueError, Exception):
                kwargs = {}
                for arg_pair in args_string.split():
                    if '=' in arg_pair:
                        key, value = arg_pair.split('=', 1)
                        kwargs[key.strip()] = value.strip()
            return kwargs

        async def ccr_execute_command(self, channel, channel_config, command_profile):
            channel_id = ccr_channel_id_string(channel.id)
            cmd_key = f"{channel_id}-{command_profile['name']}"
            lock = self.command_locks.setdefault(channel_id, asyncio.Lock())
            if lock.locked(): return False
            async with lock:
                try:
                    humanization_config = channel_config.get("humanization") or {}
                    cmd_args = command_profile.get('args', '').strip()
                    cmd_type = command_profile.get('command_type', 'prefix')
                    cmd_prefix = command_profile.get('prefix', '!')
                    
                    # Typing simulation
                    if humanization_config.get("typing", True):
                        typing_duration = random.uniform(1, 4)
                        async with channel.typing():
                            await asyncio.sleep(typing_duration)
                    
                    if cmd_type == "slash":
                        target_bot_id = ccr_safe_int(command_profile.get('bot_id', 0))
                        if not target_bot_id:
                            await self.ccr_log("Execution Error", f"**Channel**: <#{channel.id}>\n**Command**: `{command_profile['name']}`\n**Error**: Bot ID is required for slash commands", color=0xED4245)
                            return False
                        
                        try:
                            # Create future for response tracking
                            future = bot.loop.create_future()
                            self.slash_command_results[str(channel.id)] = future

                            # Register pending slash response
                            channel_id_str = ccr_channel_id_string(channel.id)
                            async with self.pending_responses_lock:
                                self.pending_slash_responses[channel_id_str] = {
                                    "cmd_name": command_profile["name"],
                                    "bot_id": target_bot_id,
                                    "timestamp": time.time(),
                                    "args": command_profile.get("args", "")
                                }
                                                        
                            # Parse arguments for slash command
                            cmd_args = command_profile.get('args', '').strip()
                            slash_kwargs = {}
                            if cmd_args:
                                slash_kwargs = self.parse_slash_arguments(cmd_args)
                            
                            # Execute the slash command using 
                            debug_mode = self.state.get('debug_mode', False) if self.state and isinstance(self.state, dict) else False
                            result = await execute_slash_command_custom(channel, target_bot_id, command_profile['name'], debug_mode=debug_mode, **slash_kwargs)
                            await asyncio.sleep(0.3)
                            
                            # Check if the command execution was successful
                            if not result.get('success', False):
                                response_data = result.get('response') or {}
                                error_details = response_data.get('error', 'Unknown error') if isinstance(response_data, dict) else 'Unknown error'
                                status_code = result.get('status_code', 0)
                                
                                # Check for specific error types that should auto-disable commands
                                if status_code == 404 and "not found" in error_details.lower():
                                    # Clean up pending response for 404 errors (command not found)
                                    async with self.pending_responses_lock:
                                        self.pending_slash_responses.pop(str(channel.id), None)
                                    self.slash_command_results.pop(str(channel.id), None)
                                    await self.ccr_log("🔴 Command Auto-Disabled", f"**Channel**: <#{channel.id}>\n**Command**: `{command_profile['name']}`\n**Bot ID**: {target_bot_id}\n**Reason**: Command not found - automatically disabled to prevent further errors", color=0xFF6B35)
                                    return False
                                elif status_code == 400 and ("10005" in str(response_data) or "unknown integration" in error_details.lower() or "integración desconocida" in error_details.lower()):
                                    if str(channel.id) in self.pending_slash_responses:
                                        self.pending_slash_responses[str(channel.id)]["initial_error"] = {
                                            "status_code": status_code,
                                            "error_details": error_details
                                        }
                                else:
                                    # Clean up pending response for other errors
                                    async with self.pending_responses_lock:
                                        self.pending_slash_responses.pop(str(channel.id), None)
                                    self.slash_command_results.pop(str(channel.id), None)
                                    await self.ccr_log("Execution Error", f"**Channel**: <#{channel.id}>\n**Command**: `{command_profile['name']}`\n**Status Code**: {status_code}\n**Error**: {error_details}", color=0xED4245)
                                    return False
                            
                            try:
                                # Wait for response via the listener
                                result = await asyncio.wait_for(future, timeout=15.0)
                                return result
                            except asyncio.TimeoutError:
                                # Check if we have a stored initial error (like 400/10005) to log instead of timeout
                                pending_data = self.pending_slash_responses.get(str(channel.id), {})
                                initial_error = pending_data.get("initial_error")
                                
                                if initial_error:
                                    # Log the original error since command didn't actually execute
                                    status_code = initial_error.get("status_code", 0)
                                    error_details = initial_error.get("error_details", "Unknown error")
                                    await self.ccr_log("🔴 Bot Not Available", f"**Channel**: <#{channel.id}>\n**Command**: `{command_profile['name']}`\n**Bot ID**: {target_bot_id}\n**Reason**: Bot not present in server (Error 10005) - Check if bot is added to server", color=0xFF6B35)
                                else:
                                    # Timeout message
                                    await self.ccr_log("Response Timeout (Slash)", f"No response received for `/{command_profile['name']}` in <#{channel.id}>.", color=0xFEE75C)
                                
                                if str(channel.id) in self.pending_slash_responses:
                                    del self.pending_slash_responses[str(channel.id)]
                                return False
                            finally:
                                if str(channel.id) in self.slash_command_results:
                                    del self.slash_command_results[str(channel.id)]
                                    
                        except Exception as e:
                            # Clean up on error
                            async with self.pending_responses_lock:
                                self.pending_slash_responses.pop(str(channel.id), None)
                            self.slash_command_results.pop(str(channel.id), None)
                            await self.ccr_log("Execution Error", f"**Channel**: <#{channel.id}>\n**Command**: `{command_profile['name']}`\n**Error**: ```{e}```", color=0xED4245)
                            return False
                    else:
                        # Execute prefix command as before
                        base_command = f"{cmd_prefix}{command_profile['name']}"
                        cmd_args = command_profile.get('args', '').strip()
                        command_to_send = f"{base_command} {cmd_args}" if cmd_args else base_command
                        await channel.send(command_to_send)
                        
                        try:
                            # Get the bot_id for this specific command
                            target_bot_id = ccr_safe_int(command_profile.get('bot_id', 0))
                            
                            # Create check function that validates both channel and bot_id if specified
                            def check(m):
                                # Check if message is in the correct channel
                                if m.channel.id != channel.id:
                                    return False
                                
                                # If bot_id is specified, validate it matches
                                if target_bot_id:
                                    # Accept message if author ID matches target_bot_id
                                    if m.author.id != target_bot_id:
                                        return False
                                else:
                                    # If no specific bot_id, only accept bot messages 
                                    if not m.author.bot:
                                        return False
                                return True
                            
                            start_time = time.time()
                            reply = await bot.wait_for("message", check=check, timeout=15.0)
                            execution_time = time.time() - start_time
                            # Include arguments in log if available
                            args_info = ""
                            if 'args' in command_profile and command_profile['args'].strip():
                                args_info = f"\n**Arguments**: `{command_profile['args']}`"
                            
                            # Get bot name if available
                            bot_name = ""
                            if hasattr(self, 'channels_cfg'):
                                bot_id_int = ccr_safe_int(str(reply.author.id), 0)
                                for channel_id, channel_config in self.channels_cfg.get("channels", {}).items():
                                    for command in channel_config.get("commands", []):
                                        if command.get("bot_id") == bot_id_int and command.get("bot_name"):
                                            bot_name = command["bot_name"]
                                            break
                                    if bot_name:
                                        break
                            bot_name_info = f"\n**Bot Name**: {bot_name}" if bot_name else ""
                            
                            log_message = f"**Command**: `{command_to_send}`{args_info}\n**Channel**: <#{channel.id}>\n**Bot ID**: {reply.author.id}{bot_name_info}"
                            await self.ccr_log("Command Executed", log_message, color=0x3498DB, message_obj=reply, execution_time=execution_time)
                            
                            debug_mode = self.state.get('debug_mode', False) if self.state and isinstance(self.state, dict) else False
                            ccr_log_to_file(f"✅ Prefix command executed: {command_to_send} in channel {channel.id} (execution time: {execution_time:.3f}s)" + "\n", level="SUCCESS", debug_mode=debug_mode, important=True)
                            
                            return True
                        except asyncio.TimeoutError:
                            # Log timeout 
                            await self.ccr_log("Response Timeout", f"No bot response for `{command_to_send}` in <#{channel.id}>.", color=0xFEE75C)
                            
                            debug_mode = self.state.get('debug_mode', False) if self.state and isinstance(self.state, dict) else False
                            ccr_log_to_file(f"⏰ Timeout: No response for {command_to_send} in channel {channel.id}", level="WARNING", debug_mode=debug_mode, important=True)
                            
                            return False
                except Exception as e:
                    # Log error
                    error_message = f"**Channel**: <#{channel.id}>\n**Command**: `{command_profile['name']}`\n**Error**: ```{e}```"
                    await self.ccr_log("Execution Error", error_message, color=0xED4245)
                    
                    debug_mode = self.state.get('debug_mode', False) if self.state and isinstance(self.state, dict) else False
                    ccr_log_to_file(f"❌ Execution error for command {command_profile['name']} in channel {channel.id}: {str(e)}", level="ERROR", debug_mode=debug_mode, important=True)
                    return False
        
        async def slash_response_listener(self, message):
            """Listens for messages and checks if they are a response to a pending slash command."""
            if not message.author.bot:
                return
            async with self.pending_responses_lock:
                if not self.pending_slash_responses:
                    return
                channel_id_str = ccr_channel_id_string(message.channel.id)
            # Check if we are waiting for a response in this channel
            if channel_id_str in self.pending_slash_responses:
                pending = self.pending_slash_responses[channel_id_str]
                
                # Safety check: ensure pending is not None and has required keys
                if not pending or not isinstance(pending, dict) or "bot_id" not in pending or "cmd_name" not in pending:
                    return
                
                if message.author.id != pending["bot_id"]:
                    return

                should_process = False
                if (message.interaction is not None and
                    message.interaction.user.id == bot.user.id and
                    message.interaction.name == pending["cmd_name"]):
                    should_process = True
                
                elif message.embeds:
                    embed_desc = message.embeds[0].description or ""
                    if "you can next" in embed_desc.lower() or "you cannot" in embed_desc.lower():
                        should_process = True

                if should_process:
                    async with self.pending_responses_lock:
                        pending_data = self.pending_slash_responses.pop(channel_id_str, None)
                    if not pending_data or not isinstance(pending_data, dict): 
                        return

                    try:
                        # Calculate execution time from when command was initiated
                        timestamp = pending_data.get('timestamp')
                        if timestamp is not None and isinstance(timestamp, (int, float)):
                            execution_time = time.time() - timestamp
                            # Ensure execution_time is not negative
                            execution_time = max(0, execution_time)
                        else:
                            execution_time = 0  # Default to 0 if timestamp is invalid
                        
                        # Log the successful response
                        command_to_send = f"/{pending_data.get('cmd_name', 'unknown')}"
                        args_info = ""
                        if 'args' in pending_data and pending_data.get('args', '').strip():
                            args_info = f"\n**Arguments**: `{pending_data['args']}`"
                        
                        # Get bot name if available
                        bot_name = ""
                        if hasattr(self, 'channels_cfg'):
                            bot_id_int = ccr_safe_int(str(message.author.id), 0)
                            for channel_id, channel_config in self.channels_cfg.get("channels", {}).items():
                                for command in channel_config.get("commands", []):
                                    if command.get("bot_id") == bot_id_int and command.get("bot_name"):
                                        bot_name = command["bot_name"]
                                        break
                                if bot_name:
                                    break
                        bot_name_info = f"\n**Bot Name**: {bot_name}" if bot_name else ""
                        
                        log_message = f"**Command**: `{command_to_send}`{args_info}\n**Channel**: <#{message.channel.id}>\n**Bot ID**: {message.author.id}{bot_name_info}"
                        await self.ccr_log("Command Executed", log_message, color=0x3498DB, message_obj=message, execution_time=execution_time)
                        
                        debug_mode = self.state.get('debug_mode', False) if self.state and isinstance(self.state, dict) else False
                        
                        future = self.slash_command_results.get(channel_id_str)
                        if future and not future.done():
                            future.set_result(True)
                    except Exception as e:
                        debug_mode = self.state.get('debug_mode', False) if self.state and isinstance(self.state, dict) else False
                        ccr_log_to_file(f"❌ Error in slash response listener: {str(e)}", level="ERROR", debug_mode=debug_mode, important=True)

                        future = self.slash_command_results.get(channel_id_str)
                        if future and not future.done():
                            future.set_exception(e)

        async def ccr_shutdown(self):
            self.running = False
            if self.scheduler_task and not self.scheduler_task.done():
                self.scheduler_task.cancel()
            if self.cleanup_task and not self.cleanup_task.done():
                self.cleanup_task.cancel()

        async def ccr_cleanup_pending_responses(self):
            """Clean up stale pending slash responses every 5 minutes"""
            while self.running:
                try:
                    await asyncio.sleep(300) 
                    if not self.running:
                        break
                    
                    current_time = time.time()
                    
                    async with self.pending_responses_lock:
                        stale_channels = []
                        # Find responses older than 30 seconds
                        for channel_id, pending_data in self.pending_slash_responses.items():
                            if current_time - pending_data.get("timestamp", 0) > 30:
                                stale_channels.append(channel_id)
                        
                    # Clean up stale responses
                    for channel_id in stale_channels:
                        removed_data = self.pending_slash_responses.pop(channel_id, None)
                        if removed_data:
                            await self.ccr_log("Cleanup", f"Removed stale pending response for /{removed_data['cmd_name']} in <#{channel_id}>", debug_mode=True)
                    
                    # Also clean up stale slash_command_results
                    stale_results = []
                    for channel_id, future in self.slash_command_results.items():
                        if future.done() or future.cancelled():
                            stale_results.append(channel_id)
                    
                    for channel_id in stale_results:
                        self.slash_command_results.pop(channel_id, None)
                        
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    await self.ccr_log("Cleanup Error", f"Error in cleanup task: {e}", color=0xED4245, debug_mode=True)
                    await asyncio.sleep(60)

        def ccr_trigger_reschedule(self): self.reschedule_event.set()
        async def ccr_scheduler_loop(self):
            while self.running:
                # Ensure state is properly initialized
                if not self.state or not isinstance(self.state, dict):
                    await asyncio.sleep(10)
                    continue
                last_used = self.state.get("last_used", {})
                try:
                    if not self.channels_cfg.get("channels"): await self.ccr_stop(); break
                    next_command_to_run, earliest_run_time = None, float('inf')
                    for channel_id, cfg in self.channels_cfg.get("channels", {}).items():
                        for cmd in cfg.get("commands", []):
                            if not cmd.get("enabled", True): continue
                            
                            # Check if command is within its timer time
                            timer_config = cmd.get("timer", {})
                            if not ccr_is_within_timer(timer_config): continue
                            
                            cmd_key = f"{channel_id}-{cmd['name']}"
                            last_run_time_raw = last_used.get(cmd_key, 0)
                            last_run_time = float(last_run_time_raw) if last_run_time_raw != 0 else 0
                            next_run_time = last_run_time + cmd.get("cooldown", 600)
                            if next_run_time < earliest_run_time:
                                earliest_run_time = next_run_time
                                next_command_to_run = {"channel_id": channel_id, "command_profile": cmd}
                    if not next_command_to_run: await asyncio.sleep(10); continue
                    sleep_duration = max(0, earliest_run_time - time.time())
                    try:
                        await asyncio.wait_for(self.reschedule_event.wait(), timeout=sleep_duration)
                        self.reschedule_event.clear()
                        continue
                    except asyncio.TimeoutError: pass
                    if not self.running: break
                    channel_id = ccr_channel_id_string(next_command_to_run["channel_id"])
                    channel = bot.get_channel(int(channel_id))
                    if channel:
                        chan_conf = self.channels_cfg["channels"][next_command_to_run["channel_id"]]
                        cmd_prof = next_command_to_run["command_profile"]
                        humanization_config = chan_conf.get("humanization") or {}
                        human_delay = humanization_config.get("human_delay") or {}
                        if human_delay.get("enabled", True):
                            await asyncio.sleep(random.uniform(human_delay.get("min", 5), human_delay.get("max", 45)))
                        # Always update last_used to respect cooldown, regardless of execution result
                        cmd_key = f"{channel.id}-{cmd_prof['name']}"
                        execution_result = await self.ccr_execute_command(channel, chan_conf, cmd_prof)
                        # Update last_used timestamp to prevent immediate re-execution on failure
                        self.state["last_used"][cmd_key] = time.time()
                        await self.ccr_save_state()
                    await asyncio.sleep(random.uniform(3, 7))
                except asyncio.CancelledError: break
                except Exception as e:
                    await self.ccr_log("Scheduler CRITICAL ERROR", f"```{e}```", color=0x992D22)
                    await asyncio.sleep(5)
            self.running = False

    def create_command_runner_ui(ccr_tab):
        ccr_ui_elements = {}
        ccr_manager_ref = lambda: bot._command_runner_manager
        
        main_container = ccr_tab.create_container(type="columns", gap=10)
        
        controls_card = main_container.create_card(width="full", height="full", gap=8)
        management_card = main_container.create_card(width="full", height="full", gap=8)
        editor_card = main_container.create_card(width="full", height="full", gap=8, visible=False)
        ccr_ui_elements["editor_card"] = editor_card
        
        # --- Event Handler Definitions ---
        async def on_ccr_master_toggle(checked):
            manager = ccr_manager_ref()
            if not manager: return
            
            # Update UI first 
            ccr_ui_elements["status_text"].content = f"Status: {'RUNNING 🟢' if checked else 'STOPPED 🔴'}"
            
            # Modify state within the lock
            async with manager.state_lock:
                manager.state["is_running"] = checked
            
            # Save the state separately to avoid deadlocks
            await manager.ccr_save_state()
            
            if checked:
                await manager.ccr_start()
            else:
                await manager.ccr_stop()
            
            action = "enabled" if checked else "disabled"
            ccr_tab.toast(type="SUCCESS", title="State Updated", description=f"Command runner has been {action}.")

        async def on_ccr_save_webhook():
            manager = ccr_manager_ref()
            if not manager: return
            url = ccr_ui_elements["webhook_input"].value
            if not url or url.startswith("https://discord.com/api/webhooks/"):
                async with manager.state_lock:
                    manager.state["webhook_url"] = url or None
                await manager.ccr_save_state()
                ccr_tab.toast(type="SUCCESS", title="Webhook Updated", description="Webhook URL saved.")
            else:
                ccr_tab.toast(type="ERROR", title="Invalid URL", description="Please enter a valid Discord webhook URL.")
        
        async def on_ccr_console_log_toggle(checked):
            manager = ccr_manager_ref()
            if not manager: return
            manager.state["console_logs_enabled"] = checked
            await manager.ccr_save_state()
            ccr_tab.toast(type="SUCCESS", title="Settings Updated", description=f"Console logs {'enabled' if checked else 'disabled'}.")

        async def on_ccr_reuse_bot_names_toggle(checked):
            manager = ccr_manager_ref()
            if not manager: return
            manager.state["reuse_bot_names"] = checked
            await manager.ccr_save_state()
            ccr_tab.toast(type="SUCCESS", title="Settings Updated", description=f"Bot name reuse {'enabled' if checked else 'disabled'}.")

        def ccr_validate_channel_id(value):
            is_valid = value.isdigit()
            ccr_ui_elements["new_channel_input"].invalid = not is_valid and value
            ccr_ui_elements["new_channel_input"].error_message = None if is_valid or not value else "ID must be a number."
            ccr_ui_elements["add_channel_button"].disabled = not is_valid
        
        def ccr_validate_timer_input(value, input_element):
            # Allow empty values
            if not value:
                input_element.invalid = False
                input_element.error_message = None
                return
            
            # Check if value contains only numbers and colon
            is_valid = all(c.isdigit() or c == ':' for c in value)
            input_element.invalid = not is_valid
            input_element.error_message = None if is_valid else "Only numbers and ':' are allowed."
        
        def ccr_validate_timer_start(value):
            ccr_validate_timer_input(value, ccr_ui_elements["timer_start_input"])
            ccr_update_save_command_button_state()
            ccr_update_add_command_button_state()
        
        def ccr_validate_timer_end(value):
            ccr_validate_timer_input(value, ccr_ui_elements["timer_end_input"])
            ccr_update_save_command_button_state()
            ccr_update_add_command_button_state()
        
        def ccr_validate_command_name(value):
            ccr_ui_elements["new_command_name_input"].invalid = False
            ccr_update_add_command_button_state()
        
        def ccr_validate_bot_id(value):
            is_valid = value.isdigit() and len(value) >= 15 if value else True
            ccr_ui_elements["new_command_bot_id_input"].invalid = not is_valid and value
            ccr_ui_elements["new_command_bot_id_input"].error_message = None if is_valid or not value else "Bot ID must be a number with at least 15 digits."
            ccr_update_add_command_button_state()
            ccr_update_save_command_button_state()
            
            # Auto-fill bot name if reuse is enabled and bot ID is valid
            manager = ccr_manager_ref()
            if manager and is_valid and value and manager.state.get("reuse_bot_names", True):
                ccr_auto_fill_bot_name(value)
        
        def ccr_auto_fill_bot_name(bot_id):
            """Auto-fill bot name based on existing commands with the same bot ID"""
            manager = ccr_manager_ref()
            if not manager or not manager.channels_cfg: return
            
            bot_name = ccr_find_existing_bot_name(manager, bot_id)
            if bot_name:
                ccr_ui_elements["new_command_bot_name_input"].value = bot_name
        
        def ccr_find_existing_bot_name(manager, bot_id):
            """Find existing bot name for the given bot ID"""
            if not manager or not manager.channels_cfg: return ""
            
            bot_id_int = ccr_safe_int(bot_id, 0)
            # Search for existing bot name with this bot ID
            for channel_id, channel_config in manager.channels_cfg.get("channels", {}).items():
                for command in channel_config.get("commands", []):
                    if command.get("bot_id") == bot_id_int and command.get("bot_name"):
                        return command["bot_name"]
            return ""
        
        def ccr_validate_cooldown(value):
            if not value or not value.strip():
                # Empty value is valid (will default to 600)
                ccr_ui_elements["new_command_cooldown_input"].invalid = False
                ccr_ui_elements["new_command_cooldown_input"].error_message = None
            else:
                # Validate the cooldown format
                parsed_cooldown = ccr_parse_time_to_seconds(value.strip())
                is_valid = parsed_cooldown is not None and parsed_cooldown >= 1
                ccr_ui_elements["new_command_cooldown_input"].invalid = not is_valid
                ccr_ui_elements["new_command_cooldown_input"].error_message = None if is_valid else "Invalid format. Use: 30s, 5m, 2h, 1d, 1w or just seconds."
            
            ccr_update_add_command_button_state()
            ccr_update_save_command_button_state()
        
        def ccr_validate_command_type(selected_items):
            ccr_update_add_command_button_state()
            ccr_update_save_command_button_state()
        
        def ccr_update_save_command_button_state():
            bot_id_valid = ccr_ui_elements["new_command_bot_id_input"].value and ccr_ui_elements["new_command_bot_id_input"].value.isdigit() and len(ccr_ui_elements["new_command_bot_id_input"].value) >= 15
            command_type_valid = ccr_ui_elements["new_command_type_select"].selected_items and len(ccr_ui_elements["new_command_type_select"].selected_items) > 0
            timer_start_valid = not ccr_ui_elements["timer_start_input"].invalid
            timer_end_valid = not ccr_ui_elements["timer_end_input"].invalid
            cooldown_valid = not ccr_ui_elements["new_command_cooldown_input"].invalid
            ccr_ui_elements["save_command_button"].disabled = not (bot_id_valid and command_type_valid and timer_start_valid and timer_end_valid and cooldown_valid)
        
        def ccr_update_add_command_button_state():
            bot_id_valid = ccr_ui_elements["new_command_bot_id_input"].value and ccr_ui_elements["new_command_bot_id_input"].value.isdigit() and len(ccr_ui_elements["new_command_bot_id_input"].value) >= 15
            name_valid = ccr_ui_elements["new_command_name_input"].value and ccr_ui_elements["new_command_name_input"].value.strip()
            command_type_valid = ccr_ui_elements["new_command_type_select"].selected_items and len(ccr_ui_elements["new_command_type_select"].selected_items) > 0
            timer_start_valid = not ccr_ui_elements["timer_start_input"].invalid
            timer_end_valid = not ccr_ui_elements["timer_end_input"].invalid
            cooldown_valid = not ccr_ui_elements["new_command_cooldown_input"].invalid
            ccr_ui_elements["add_command_button_new"].disabled = not (bot_id_valid and name_valid and command_type_valid and timer_start_valid and timer_end_valid and cooldown_valid)

        def ccr_load_channel_to_editor(selected_ids: list):
            manager = ccr_manager_ref()
            if not manager or not selected_ids: 
                editor_card.visible = False
                ccr_ui_elements["command_quick_select"].items = [{'id': 'no_commands', 'title': 'No commands available', 'disabled': True}]
                ccr_ui_elements["command_quick_select"].disabled = True
                ccr_ui_elements["editor_title"].content = "Editing Templeate"  # Reset title when no channel selected
                
                # Clear all command control inputs
                ccr_ui_elements["new_command_name_input"].value = ""
                ccr_ui_elements["new_command_args_input"].value = ""
                ccr_ui_elements["new_command_bot_id_input"].value = ""
                ccr_ui_elements["new_command_bot_name_input"].value = ""
                ccr_ui_elements["new_command_cooldown_input"].value = ""
                ccr_ui_elements["new_command_prefix_input"].value = ""
                ccr_ui_elements["timer_start_input"].value = ""
                ccr_ui_elements["timer_end_input"].value = ""
                ccr_ui_elements["new_command_type_select"].selected_items = []
                ccr_ui_elements["timer_days_select"].selected_items = []

                # Reset button states
                ccr_ui_elements["add_command_button_new"].visible = True
                ccr_ui_elements["save_command_button"].visible = False

                # Hide all command slots and set gap to 0
                for slot in ccr_ui_elements.get("command_slots", []):
                    slot["group"].visible = False
                    slot["toggle"].visible = False
                    slot["group"].gap = 0
                return
            cfg = manager.channels_cfg["channels"].get(str(selected_ids[0]))
            if cfg:
                # Clear command selector first to reset editing state
                ccr_ui_elements["command_quick_select"].selected_items = []
                # Preserve current editor input values instead of clearing them
                # Only reset button states to Add mode
                ccr_ui_elements["add_command_button_new"].visible = True
                ccr_ui_elements["save_command_button"].visible = False
                
                manager.ccr_populate_editor(cfg, channel_id=selected_ids[0], ccr_manager_ref=ccr_manager_ref, ccr_tab=ccr_tab, ccr_update_command_selector=ccr_update_command_selector)
                editor_card.visible = True
                # Update command selector with commands from this channel
                ccr_update_command_selector(cfg.get("commands", []))
            else:
                ccr_ui_elements["command_quick_select"].items = [{'id': 'no_commands', 'title': 'No commands available', 'disabled': True}]
                ccr_ui_elements["command_quick_select"].disabled = True
                ccr_ui_elements["editor_title"].content = "Channel Editor"  # Reset title when channel has no config
                # Clear all command control inputs
                ccr_ui_elements["new_command_name_input"].value = ""
                ccr_ui_elements["new_command_args_input"].value = ""
                ccr_ui_elements["new_command_bot_id_input"].value = ""
                ccr_ui_elements["new_command_cooldown_input"].value = ""
                ccr_ui_elements["new_command_prefix_input"].value = ""
                ccr_ui_elements["timer_start_input"].value = ""
                ccr_ui_elements["timer_end_input"].value = ""
                ccr_ui_elements["new_command_type_select"].selected_items = []
                ccr_ui_elements["timer_days_select"].selected_items = []
                # Reset button states
                ccr_ui_elements["add_command_button_new"].visible = True
                ccr_ui_elements["save_command_button"].visible = False
                # Hide all command slots and set gap to 0
                for slot in ccr_ui_elements.get("command_slots", []):
                    slot["group"].visible = False
                    slot["toggle"].visible = False
                    slot["group"].gap = 0
                editor_card.visible = False

        # Helper function for escaping
        def robust_escape(value):
            if value is None:
                return ""
            str_value = str(value)
            str_value = str_value.replace('\\', '\\\\')
            str_value = str_value.replace('"', '\\"')
            str_value = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', str_value)
            return str_value

        def ccr_update_command_selector(commands):
            if not commands:
                ccr_ui_elements["command_quick_select"].items = [{'id': 'no_commands', 'title': 'No commands available', 'disabled': True}]
                ccr_ui_elements["command_quick_select"].disabled = True
            else:
                command_items = []
                for i, cmd in enumerate(commands):
                    # Escape command name to prevent JavaScript syntax errors
                    cmd_name = cmd.get('name', 'Unnamed')
                    cmd_type = cmd.get('command_type', 'prefix')
                    bot_name = cmd.get('bot_name', '')
                    bot_id = cmd.get('bot_id', '')
                    
                    # Use custom bot name if provided, otherwise use bot ID
                    bot_display = bot_name if bot_name else str(bot_id)
                    
                    safe_name = robust_escape(cmd_name)
                    safe_type = robust_escape(cmd_type)
                    safe_bot_display = robust_escape(bot_display)
                    command_items.append({
                        'id': str(i),
                        'title': f"{safe_name} ({safe_type}) - Bot: {safe_bot_display}"
                    })
                ccr_ui_elements["command_quick_select"].items = command_items
                ccr_ui_elements["command_quick_select"].disabled = False
                ccr_ui_elements["command_quick_select"].selected_items = []

        def ccr_load_command_to_editor(selected_ids: list):
            manager = ccr_manager_ref()
            if not manager or not selected_ids:
                ccr_clear_editor_for_new_command()
                return
            
            channel_id = ccr_ui_elements["channel_quick_select"].selected_items[0] if ccr_ui_elements["channel_quick_select"].selected_items else None
            if not channel_id:
                return
                
            cfg = manager.channels_cfg["channels"].get(str(channel_id))
            if not cfg:
                return
                
            command_index = ccr_safe_int(selected_ids[0], 0)
            commands = cfg.get("commands", [])
            if command_index >= len(commands):
                return
                
            command = commands[command_index]
            ccr_populate_editor_with_command(command)
            
            # Show Save button, hide Add button
            ccr_ui_elements["add_command_button_new"].visible = False
            ccr_ui_elements["save_command_button"].visible = True
            ccr_ui_elements["save_command_button"].disabled = False
            
            # Store the command index for saving later
            ccr_ui_elements["save_command_button"].command_index = command_index

        def ccr_clear_editor_for_new_command():
            # Clear all editor fields
            ccr_ui_elements["new_command_name_input"].value = ""
            ccr_ui_elements["new_command_args_input"].value = ""
            ccr_ui_elements["new_command_bot_id_input"].value = ""
            ccr_ui_elements["new_command_bot_name_input"].value = ""
            ccr_ui_elements["new_command_cooldown_input"].value = ""
            ccr_ui_elements["new_command_type_select"].selected_items = []
            ccr_ui_elements["new_command_prefix_input"].value = ""
            
            # Clear timer configuration fields
            ccr_ui_elements["timer_start_input"].value = ""
            ccr_ui_elements["timer_end_input"].value = ""
            ccr_ui_elements["timer_days_select"].selected_items = []
            
            # Show Add button, hide Save button
            ccr_ui_elements["add_command_button_new"].visible = True
            ccr_ui_elements["save_command_button"].visible = False
            
            # Clear command selector
            ccr_ui_elements["command_quick_select"].selected_items = []
            
            # Update button states
            ccr_update_add_command_button_state()
            ccr_update_save_command_button_state()

        def ccr_populate_editor_with_command(command):
            # Helper function to safely escape values for UI
            def safe_value(value, default=""):
                if value is None:
                    return default
                # Convert to string and handle potential problematic characters
                str_value = str(value)
                # Replace problematic characters that could cause JavaScript syntax errors
                str_value = str_value.replace('\\', '\\\\')
                str_value = str_value.replace('"', '\\"')
                str_value = str_value.replace("'", "\\'")
                str_value = str_value.replace('\n', '\\n')
                str_value = str_value.replace('\r', '\\r')
                str_value = str_value.replace('\t', '\\t')
                # Handle ANSI escape sequences and other problematic characters
                str_value = str_value.replace('\u001b', '\\u001b')
                str_value = str_value.replace('`', '\\`')
                str_value = str_value.replace('$', '\\$')
                # Remove or escape other control characters that could break JavaScript
                str_value = re.sub(r'[\x00-\x1f\x7f-\x9f]', lambda m: f'\\u{ord(m.group()):04x}', str_value)
                return str_value
            
            ccr_ui_elements["new_command_name_input"].value = safe_value(command.get("name", ""))
            ccr_ui_elements["new_command_args_input"].value = safe_value(command.get("args", ""))
            ccr_ui_elements["new_command_bot_id_input"].value = safe_value(command.get("bot_id", ""))
            ccr_ui_elements["new_command_bot_name_input"].value = safe_value(command.get("bot_name", ""))
            ccr_ui_elements["new_command_cooldown_input"].value = safe_value(command.get("cooldown_display", command.get("cooldown", 600)))
            ccr_ui_elements["new_command_type_select"].selected_items = [safe_value(command.get("command_type", "prefix"))]
            ccr_ui_elements["new_command_prefix_input"].value = safe_value(command.get("prefix", ""))
            
            # Load timer configuration
            timer_config = command.get("timer", {})
            ccr_ui_elements["timer_start_input"].value = safe_value(timer_config.get("start_time", ""))
            ccr_ui_elements["timer_end_input"].value = safe_value(timer_config.get("end_time", ""))
            ccr_ui_elements["timer_days_select"].selected_items = timer_config.get("days", [])
            
            # Update Save Command button state
            ccr_update_save_command_button_state()
            ccr_update_add_command_button_state()

        async def on_ccr_save_command():
            manager = ccr_manager_ref()
            if not manager:
                return
                
            channel_id = ccr_ui_elements["channel_quick_select"].selected_items[0] if ccr_ui_elements["channel_quick_select"].selected_items else None
            if not channel_id:
                ccr_tab.toast(type="ERROR", title="No Channel", description="Please select a channel first.")
                return
                
            command_index = getattr(ccr_ui_elements["save_command_button"], 'command_index', None)
            if command_index is None:
                ccr_tab.toast(type="ERROR", title="No Command", description="No command selected for editing.")
                return
                
            cfg = manager.channels_cfg["channels"].get(str(channel_id))
            if not cfg:
                return
                
            commands = cfg.get("commands", [])
            if command_index >= len(commands):
                ccr_tab.toast(type="ERROR", title="Invalid Command", description="Selected command no longer exists.")
                return
                
            # Update the command with new values
            cooldown_input = ccr_ui_elements["new_command_cooldown_input"].value.strip()
            cooldown_display = cooldown_input if cooldown_input else "600"
            cooldown_seconds = ccr_parse_time_to_seconds(cooldown_input) or 600
            
            updated_command = {
                "name": ccr_ui_elements["new_command_name_input"].value.strip(),
                "args": ccr_ui_elements["new_command_args_input"].value.strip(),
                "bot_id": ccr_safe_int(ccr_ui_elements["new_command_bot_id_input"].value, 0),
                "bot_name": ccr_ui_elements["new_command_bot_name_input"].value.strip(),
                "cooldown": cooldown_seconds,
                "cooldown_display": cooldown_display,
                "command_type": ccr_ui_elements["new_command_type_select"].selected_items[0] if ccr_ui_elements["new_command_type_select"].selected_items else "prefix",
                "prefix": ccr_ui_elements["new_command_prefix_input"].value.strip(),
                "timer": {"enabled": False},  # Default timer
                "enabled": True  # Default enabled state
            }
            
            # Preserve existing fields first
            old_command = commands[command_index]
            
            # Preserve the original enabled state
            updated_command["enabled"] = old_command.get("enabled", True)
            
            # Handle timer configuration based on UI inputs
            start_time = ccr_ui_elements["timer_start_input"].value.strip()
            end_time = ccr_ui_elements["timer_end_input"].value.strip()
            selected_days = ccr_ui_elements["timer_days_select"].selected_items
            
            # Format and validate time inputs
            def format_time_input(time_str):
                if not time_str:
                    return time_str
                
                # If it's just a number (like "9" or "13")
                if time_str.isdigit():
                    hour = int(time_str)
                    # Validate hour range (0-23)
                    if hour >= 24:
                        ccr_tab.toast(type="ERROR", title="Invalid Time", description=f"Hour {hour} is invalid. Please use 0-23.")
                        return None
                    return f"{hour:02d}:00"
                
                # If it contains a colon, validate the format
                if ":" in time_str:
                    try:
                        hour_part, minute_part = time_str.split(":")
                        hour = int(hour_part)
                        minute = int(minute_part)
                        
                        # Special case: if minute is single digit (like 5), treat as 50
                        if len(minute_part) == 1 and minute <= 5:
                            minute = minute * 10
                        
                        if hour >= 24 or minute >= 60:
                            ccr_tab.toast(type="ERROR", title="Invalid Time", description=f"Time {time_str} is invalid. Use HH:MM format (0-23:0-59).")
                            return None
                        
                        return f"{hour:02d}:{minute:02d}"
                    except ValueError:
                        ccr_tab.toast(type="ERROR", title="Invalid Time Format", description=f"Time {time_str} has invalid format. Use HH:MM or just hour number.")
                        return None
                
                return time_str
            
            # Format the time inputs
            formatted_start_time = format_time_input(start_time)
            formatted_end_time = format_time_input(end_time)
            
            # Check if formatting failed (invalid input)
            if (start_time and formatted_start_time is None) or (end_time and formatted_end_time is None):
                return  # Stop execution if invalid time format
            
            # Check if any timer fields have values
            has_timer_config = bool(formatted_start_time or formatted_end_time or selected_days)
            
            if has_timer_config:
                # Save timer configuration from UI
                updated_command["timer"] = {
                    "enabled": True,
                    "start_time": formatted_start_time or "",
                    "end_time": formatted_end_time or "",
                    "days": selected_days
                }
            else:
                # No timer configuration in UI - check if we should preserve or remove
                if "timer" in old_command:
                    # Timer exists but UI is empty - remove timer (user cleared it)
                    pass  # Don't add timer field, effectively removing it
                else:
                    # No timer in original and no UI config - add default disabled timer
                    updated_command["timer"] = {"enabled": False}
            
            # Preserve slash_type if it exists
            if "slash_type" in old_command:
                updated_command["slash_type"] = old_command["slash_type"]
            
            # Preserve any other fields that might exist
            for key in old_command:
                if key not in updated_command:
                    updated_command[key] = old_command[key]
                    
            commands[command_index] = updated_command
            
            await manager.ccr_save_channels()
            
            # Trigger reschedule to wake up the scheduler immediately
            manager.ccr_trigger_reschedule()
            
            ccr_tab.toast(type="SUCCESS", title="Command Updated", description="The command has been successfully updated.")
            
            # Clear editor and return to Add Command mode
            ccr_clear_editor_for_new_command()
            
            # Refresh the command selector
            ccr_update_command_selector(commands)
            
            # Update UI to reflect the new command name in toggles
            await manager.ccr_connect_and_populate_ui()
            
            # Clear selection and return to add mode
            ccr_clear_editor_for_new_command()

        async def on_ccr_add_channel():
            manager = ccr_manager_ref()
            if not manager: return
            channel_id = ccr_ui_elements["new_channel_input"].value
            if channel_id in manager.channels_cfg["channels"]:
                ccr_tab.toast(type="ERROR", title="Already Exists", description="This channel is already configured.")
                return
            if not bot.get_channel(int(channel_id)):
                ccr_tab.toast(type="ERROR", title="Not Found", description="Could not find this channel.")
                return
            
            # Create empty configuration for new channel
            new_cfg = {
                "commands": [],
                "humanization": {
                    "typing": True,
                    "human_delay": {
                        "enabled": True,
                        "min": 5,
                        "max": 45
                    }
                }
            }
            manager.channels_cfg["channels"][channel_id] = new_cfg
            await manager.ccr_save_channels()
            ccr_tab.toast(type="SUCCESS", title="Channel Added", description=f"Channel {channel_id} added.")
            ccr_ui_elements["new_channel_input"].value = ""
            ccr_ui_elements["channel_quick_select"].selected_items = [channel_id]
            # Automatically load the newly added channel into the editor
            ccr_load_channel_to_editor([channel_id])

        def ccr_get_config_from_editor_slots(existing_commands=None):
            commands = []
            existing_commands = existing_commands or []
            for i, s in enumerate(ccr_ui_elements["command_slots"]):
                if s["group"].visible:
                    # Get the original command data to preserve all properties
                    original_cmd = existing_commands[i] if i < len(existing_commands) else {}
                    
                    command_data = {
                        "name": s.get("original_name", s["toggle"].label),
                        "args": original_cmd.get("args", ""),
                        "bot_id": original_cmd.get("bot_id", ""),
                        "bot_name": original_cmd.get("bot_name", ""),
                        "cooldown": original_cmd.get("cooldown", 600),
                        "cooldown_display": original_cmd.get("cooldown_display", "600"),
                        "command_type": original_cmd.get("command_type", "prefix"),
                        "prefix": original_cmd.get("prefix", "!"),
                        "timer": {"enabled": False},  
                        "enabled": s["toggle"].checked
                    }
                    
                    # Preserve timer configuration from original command
                    if "timer" in original_cmd:
                        command_data["timer"] = original_cmd["timer"].copy()
                    
                    # ALWAYS preserve slash_type if the original command had it, regardless of enabled state
                    original_slash_type = original_cmd.get("slash_type")
                    if original_slash_type and original_slash_type != 'None':
                        # Clean up malformed values (whitespace, empty strings)
                        cleaned_slash_type = original_slash_type.strip()
                        if cleaned_slash_type and cleaned_slash_type in ["server", "global"]:
                            command_data["slash_type"] = cleaned_slash_type

                    
                    # ALWAYS preserve execution_type if it exists, regardless of enabled state
                    original_execution_type = original_cmd.get("execution_type")
                    if original_execution_type and original_execution_type != 'None':
                        cleaned_execution_type = original_execution_type.strip()
                        if cleaned_execution_type and cleaned_execution_type in ["direct", "api"]:
                            command_data["execution_type"] = cleaned_execution_type

                    # Set default execution_type if not present
                    elif not command_data.get("execution_type"):
                        command_data["execution_type"] = "direct"

                    
                    # Add timer configuration if available in UI
                    try:
                        timer_start = ccr_ui_elements["timer_start_input"].value.strip() if ccr_ui_elements["timer_start_input"].value else ""
                        timer_end = ccr_ui_elements["timer_end_input"].value.strip() if ccr_ui_elements["timer_end_input"].value else ""
                        timer_days = ccr_ui_elements["timer_days_select"].selected_items or []
                        
                        if timer_start and timer_end:
                              command_data["timer"] = {
                                  "enabled": True,
                                  "start_time": timer_start,
                                  "end_time": timer_end,
                                  "days": timer_days if timer_days else []
                              }
                    except AttributeError:
                        pass
                    
                    commands.append(command_data)
            return {"humanization": {"typing": ccr_ui_elements["typing_toggle"].checked, "human_delay": {"enabled": ccr_ui_elements["human_delay_toggle"].checked, "min": ccr_safe_int(ccr_ui_elements["min_delay_input"].value, 5), "max": ccr_safe_int(ccr_ui_elements["max_delay_input"].value, 45)}}, "commands": commands}

        async def on_ccr_add_new_command():
            manager = ccr_manager_ref()
            if not manager: return
            channel_id = manager.ui_state.get("selected_channel_id")
            if not channel_id: ccr_tab.toast(type="ERROR", title="Error", description="Select a channel first."); return
            try:
                cmd_name_value = ccr_ui_elements["new_command_name_input"].value
                cmd_name = cmd_name_value.strip() if cmd_name_value else ""
            except AttributeError:
                cmd_name = ""
            if not cmd_name: ccr_tab.toast(type="ERROR", title="Error", description="The command must have a name."); return
            
            try:
                cmd_args_value = ccr_ui_elements["new_command_args_input"].value
                cmd_args = cmd_args_value.strip() if cmd_args_value else ""
            except AttributeError:
                cmd_args = ""
            
            try:
                cmd_bot_id_value = ccr_ui_elements["new_command_bot_id_input"].value
                cmd_bot_id = cmd_bot_id_value.strip() if cmd_bot_id_value else ""
            except AttributeError:
                cmd_bot_id = ""
            
            try:
                cmd_bot_name_value = ccr_ui_elements["new_command_bot_name_input"].value
                cmd_bot_name = cmd_bot_name_value.strip() if cmd_bot_name_value else ""
            except AttributeError:
                cmd_bot_name = ""
            
            if not cmd_bot_name and manager.state.get("reuse_bot_names", True) and cmd_bot_id:
                cmd_bot_name = ccr_find_existing_bot_name(manager, cmd_bot_id)
            
            try:
                cmd_type_value = ccr_ui_elements["new_command_type_select"].selected_items
                cmd_type = cmd_type_value[0] if cmd_type_value else "prefix"
            except (AttributeError, IndexError):
                cmd_type = "prefix"
            
            try:
                cmd_prefix_value = ccr_ui_elements["new_command_prefix_input"].value
                cmd_prefix = cmd_prefix_value.strip() if cmd_prefix_value else "!"
            except AttributeError:
                cmd_prefix = "!"
            
            try:
                cmd_cooldown_value = ccr_ui_elements["new_command_cooldown_input"].value
                if cmd_cooldown_value and cmd_cooldown_value.strip():
                    cmd_cooldown_original = cmd_cooldown_value.strip()
                    cmd_cooldown = ccr_parse_time_to_seconds(cmd_cooldown_original)
                    if cmd_cooldown is None or cmd_cooldown < 1:
                        ccr_tab.toast(type="ERROR", title="Error", description="Invalid cooldown format. Use: 30s, 5m, 2h, 1d, 1w or just seconds.")
                        return
                else:
                    cmd_cooldown_original = "600"
                    cmd_cooldown = 600
            except (AttributeError, ValueError):
                cmd_cooldown_original = "600"
                cmd_cooldown = 600
            
            # Get timer configuration
            try:
                timer_start = ccr_ui_elements["timer_start_input"].value.strip() if ccr_ui_elements["timer_start_input"].value else ""
                timer_end = ccr_ui_elements["timer_end_input"].value.strip() if ccr_ui_elements["timer_end_input"].value else ""
                timer_days = ccr_ui_elements["timer_days_select"].selected_items or []
            except AttributeError:
                timer_start = ""
                timer_end = ""
                timer_days = []
            
            if not cmd_bot_id: 
                ccr_tab.toast(type="ERROR", title="Error", description="The Bot ID is required to add a command."); 
                return
            
            if not (cmd_bot_id.isdigit() and len(cmd_bot_id) >= 15):
                ccr_tab.toast(type="ERROR", title="Error", description="The Bot ID must be a number with at least 15 digits.");
                return
            
            config = manager.channels_cfg["channels"].get(channel_id, {})
            commands = config.setdefault("commands", [])
            if any(c.get("name") == cmd_name and c.get("bot_id") == ccr_safe_int(cmd_bot_id, 0) for c in commands): ccr_tab.toast(type="ERROR", title="Error", description="Command name already exists for this bot."); return
            
            # Create command with timer configuration
            new_command = {
                "name": cmd_name, 
                "args": cmd_args, 
                "bot_id": ccr_safe_int(cmd_bot_id, 0), 
                "bot_name": cmd_bot_name,
                "command_type": cmd_type, 
                "prefix": cmd_prefix, 
                "cooldown": cmd_cooldown,
                "cooldown_display": cmd_cooldown_original,
                "enabled": True
            }
            
            # Add timer if configured (days are optional)
            if timer_start and timer_end:
                new_command["timer"] = {
                    "enabled": True,
                    "start_time": timer_start,
                    "end_time": timer_end,
                    "days": timer_days if timer_days else []
                }
            
            commands.append(new_command)
            await manager.ccr_save_channels()
            ccr_ui_elements["new_command_name_input"].value = ""
            ccr_ui_elements["new_command_args_input"].value = ""
            ccr_ui_elements["new_command_bot_id_input"].value = ""
            ccr_ui_elements["new_command_bot_name_input"].value = ""
            ccr_ui_elements["new_command_cooldown_input"].value = ""
            ccr_ui_elements["new_command_type_select"].selected_items = ["prefix"]
            ccr_ui_elements["new_command_prefix_input"].value = "!"
            ccr_ui_elements["timer_start_input"].value = ""
            ccr_ui_elements["timer_end_input"].value = ""
            ccr_ui_elements["timer_days_select"].selected_items = []
            manager.ccr_populate_editor(config, channel_id, ccr_manager_ref=ccr_manager_ref, ccr_tab=ccr_tab, ccr_update_command_selector=ccr_update_command_selector)
            # Update command selector with new command list
            ccr_update_command_selector(commands)
            manager.ccr_trigger_reschedule()
            ccr_tab.toast(type="SUCCESS", title="Command Added", description="The new command has been successfully added to the channel.")

        async def on_ccr_save_changes():
            manager = ccr_manager_ref()
            if not manager: return
            channel_id = manager.ui_state.get("selected_channel_id")
            if not channel_id: ccr_tab.toast(type="ERROR", title="Error", description="No channel loaded to save."); return
            
            # Get existing configuration to preserve other settings
            existing_config = manager.channels_cfg["channels"][channel_id].copy()
            existing_commands = existing_config.get("commands", [])
            
            # Get updated configuration from editor
            updated_config = ccr_get_config_from_editor_slots(existing_commands)
            
            # Check for cooldown changes that might trigger immediate execution
            new_commands = updated_config.get("commands", [])
            last_used = manager.state.get("last_used", {})
            current_time = time.time()
            
            for i, new_cmd in enumerate(new_commands):
                if i < len(existing_commands):
                    old_cmd = existing_commands[i]
                    old_cooldown = old_cmd.get("cooldown", 600)
                    new_cooldown = new_cmd.get("cooldown", 600)
                    
                    # Check if cooldown was reduced and command is enabled
                    if new_cooldown < old_cooldown and new_cmd.get("enabled", True):
                        cmd_key = f"{channel_id}-{new_cmd.get('name', '')}"
                        last_run_time_raw = last_used.get(cmd_key, 0)
                        last_run_time = float(last_run_time_raw) if last_run_time_raw != 0 else 0
                        
                        # If enough time has passed for the new cooldown, reset last_used to trigger immediate execution
                        if last_run_time > 0 and (current_time - last_run_time) >= new_cooldown:
                            last_used[cmd_key] = current_time - new_cooldown
                            manager.state["last_used"] = last_used
                            await manager.ccr_save_state()
            
            # Merge configurations, preserving existing settings not handled by editor
            for key, value in updated_config.items():
                existing_config[key] = value
            manager.channels_cfg["channels"][channel_id] = existing_config
            await manager.ccr_save_channels()
            ccr_tab.toast(type="SUCCESS", title="Changes Saved", description=f"Configuration for channel {channel_id} updated.")
            
            # Update UI to reflect any command name changes in toggles
            await manager.ccr_connect_and_populate_ui()
            
            manager.ccr_trigger_reschedule()

        async def on_ccr_delete_channel():
            manager = ccr_manager_ref()
            if not manager: return
            channel_id = manager.ui_state.get("selected_channel_id")
            if not channel_id: return
            await manager.ccr_remove_channel(channel_id)
            ccr_tab.toast(type="SUCCESS", title="Channel Deleted", description=f"Channel {channel_id} removed.")
            editor_card.visible = False
            # Clear the Quick Select and return to template
            ccr_ui_elements["channel_quick_select"].selected_items = []
            manager.ui_state["selected_channel_id"] = None
            # Reset editor title to default state
            ccr_ui_elements["editor_title"].content = "Channel Editor"
            # Clear all Command Control fields
            ccr_clear_editor_for_new_command()
            # Reset the editor state including gap
            ccr_load_channel_to_editor([])

        # --- UI Element Creation ---        
        # Card 1
        controls_card.create_ui_element(UI.Text, content="Global Controls", size="xl", weight="bold")
        ccr_ui_elements["master_toggle"] = controls_card.create_ui_element(UI.Toggle, label="Enable Runner", onChange=on_ccr_master_toggle, disabled=True)
        ccr_ui_elements["status_text"] = controls_card.create_ui_element(UI.Text, content="Status: Loading...", color="var(--text-muted)")
        controls_card.create_ui_element(UI.Text, content="Settings", size="lg", weight="bold", margin="mt-4")
        ccr_ui_elements["webhook_input"] = controls_card.create_ui_element(UI.Input, label="Webhook URL", full_width=True)
        controls_card.create_ui_element(UI.Button, label="Save Webhook", color="primary", full_width=True, onClick=on_ccr_save_webhook)
        ccr_ui_elements["reuse_bot_names_toggle"] = controls_card.create_ui_element(UI.Toggle, label="Reuse Bot Names", onChange=on_ccr_reuse_bot_names_toggle)
        ccr_ui_elements["console_logs_toggle"] = controls_card.create_ui_element(UI.Toggle, label="Console Logs", onChange=on_ccr_console_log_toggle)
        
        # Card 2
        management_card.create_ui_element(UI.Text, content="Channel Profiles", size="xl", weight="bold")
        ccr_ui_elements["channel_quick_select"] = management_card.create_ui_element(UI.Select, label="Quick Select Channel", full_width=True, disabled=True, onChange=ccr_load_channel_to_editor, items=[{'id': 'loading', 'title': 'Cargando canales...', 'disabled': True}])
        ccr_ui_elements["command_quick_select"] = management_card.create_ui_element(UI.Select, label="Select Command to Edit", full_width=True, disabled=True, onChange=ccr_load_command_to_editor, items=[{'id': 'no_commands', 'title': 'No commands available', 'disabled': True}])
        management_card.create_ui_element(UI.Text, content="Add a New Channel:", weight="medium", margin="mt-4")
        ccr_ui_elements["new_channel_input"] = management_card.create_ui_element(UI.Input, label="Channel ID", placeholder="Enter Channel ID...", onInput=ccr_validate_channel_id, disabled=True)
        ccr_ui_elements["add_channel_button"] = management_card.create_ui_element(UI.Button, label="Add Channel", color="primary", full_width=True, margin="mt-2", disabled=True, onClick=on_ccr_add_channel)
        
        # Card 3
        ccr_ui_elements["editor_title"] = editor_card.create_ui_element(UI.Text, content="Channel Editor", size="xl", weight="bold")
        new_cmd_group = editor_card.create_group(type="columns", gap=8, full_width=True)
        ccr_ui_elements["new_command_name_input"] = new_cmd_group.create_ui_element(UI.Input, label="New Command Name", onInput=ccr_validate_command_name)
        ccr_ui_elements["add_command_button_new"] = new_cmd_group.create_ui_element(UI.Button, label="Add Command", color="primary", onClick=on_ccr_add_new_command, disabled=True)
        ccr_ui_elements["save_command_button"] = new_cmd_group.create_ui_element(UI.Button, label="Save Command", color="success", onClick=on_ccr_save_command, disabled=True, visible=False)
        ccr_ui_elements["new_command_args_input"] = editor_card.create_ui_element(UI.Input, label="Command Arguments", placeholder="winners=2 prize=\"Nitro Monthly\"", full_width=True)

        ccr_ui_elements["new_command_bot_id_input"] = editor_card.create_ui_element(UI.Input, label="Bot ID", placeholder="Bot ID to verify response", full_width=True, onInput=ccr_validate_bot_id)
        ccr_ui_elements["new_command_bot_name_input"] = editor_card.create_ui_element(UI.Input, label="Bot Name (Optional)", placeholder="Custom name for this bot", full_width=True)
        ccr_ui_elements["new_command_cooldown_input"] = editor_card.create_ui_element(UI.Input, label="Cooldown", placeholder="10m, 2h, 1d, 600s or just 600", full_width=True, onInput=ccr_validate_cooldown)
        new_cmd_type_group = editor_card.create_group(type="columns", gap=8, full_width=True)
        ccr_ui_elements["new_command_type_select"] = new_cmd_type_group.create_ui_element(UI.Select, label="Command Type", items=[{"id": "prefix", "title": "Prefix"}, {"id": "slash", "title": "Slash"}], full_width=True, onChange=ccr_validate_command_type)
        ccr_ui_elements["new_command_prefix_input"] = new_cmd_type_group.create_ui_element(UI.Input, label="Custom Prefix", placeholder="e.g., '!'", full_width=True)
        
        # Timer Configuration
        editor_card.create_ui_element(UI.Text, content="Timer Configuration", weight="bold", size="lg", margin="mt-4")
        timer_group = editor_card.create_group(type="columns", gap=8, full_width=True)
        ccr_ui_elements["timer_start_input"] = timer_group.create_ui_element(UI.Input, label="Start Time", placeholder="09:00", full_width=True, onInput=ccr_validate_timer_start)
        ccr_ui_elements["timer_end_input"] = timer_group.create_ui_element(UI.Input, label="End Time", placeholder="17:00", full_width=True, onInput=ccr_validate_timer_end)
        ccr_ui_elements["timer_days_select"] = editor_card.create_ui_element(UI.Select, label="Active Days", mode="multiple", items=[
            {"id": "monday", "title": "Monday"},
            {"id": "tuesday", "title": "Tuesday"},
            {"id": "wednesday", "title": "Wednesday"},
            {"id": "thursday", "title": "Thursday"},
            {"id": "friday", "title": "Friday"},
            {"id": "saturday", "title": "Saturday"},
            {"id": "sunday", "title": "Sunday"}
        ], full_width=True)
        editor_card.create_ui_element(UI.Text, content="Humanization", weight="bold", size="lg", margin="mt-4")
        ccr_ui_elements["typing_toggle"] = editor_card.create_ui_element(UI.Toggle, label="Simulate Typing")
        ccr_ui_elements["human_delay_toggle"] = editor_card.create_ui_element(UI.Toggle, label="Enable Human Delay")
        jitter_group = editor_card.create_group(type="columns", gap=8, full_width=True)
        ccr_ui_elements["min_delay_input"] = jitter_group.create_ui_element(UI.Input, label="Min Delay (s)", placeholder="5")
        ccr_ui_elements["max_delay_input"] = jitter_group.create_ui_element(UI.Input, label="Max Delay (s)", placeholder="45")
        editor_card.create_ui_element(UI.Text, content="Command Control", weight="bold", size="lg", margin="mt-4")
        command_control_group = editor_card.create_group(type="rows", gap=4, full_width=True)
        ccr_ui_elements["no_commands_text"] = command_control_group.create_ui_element(UI.Text, content="No commands configured.", color="var(--text-muted)", visible=False)
        # Command slots will be created dynamically
        
        # Initialize with empty command slots list - will be populated dynamically
        ccr_ui_elements["command_slots"] = []
        ccr_ui_elements["command_control_group"] = command_control_group  # Store reference for dynamic slot creation
        editor_action_buttons = editor_card.create_group(type="columns", gap=8, margin="mt-8")
        editor_action_buttons.create_ui_element(UI.Button, label="Save Changes", color="primary", onClick=on_ccr_save_changes)
        editor_action_buttons.create_ui_element(UI.Button, label="Delete Channel", color="danger", onClick=on_ccr_delete_channel)
        
        return ccr_ui_elements

    async def ccr_main_initializer(ccr_ui_elements):
        try:
            if not hasattr(bot, '_command_runner_lock'):
                bot._command_runner_lock = asyncio.Lock()
            
            async with bot._command_runner_lock:
                if hasattr(bot, '_command_runner_manager') and bot._command_runner_manager:
                    await bot._command_runner_manager.ccr_shutdown()
                
                manager = CommandRunnerManager()
                bot._command_runner_manager = manager
                
                # Register the slash response listener
                @bot.listen("on_message")
                async def ccr_slash_response_listener(message):
                    if hasattr(bot, '_command_runner_manager') and bot._command_runner_manager:
                        await bot._command_runner_manager.slash_response_listener(message)
                
                manager.ccr_set_ui_elements(ccr_ui_elements)
                await manager.ccr_load_initial_data()
                await manager.ccr_connect_and_populate_ui()
                if manager.state.get("is_running", False):
                    await manager.ccr_start()
        
        except Exception as e:
            error_details = traceback.format_exc()
            print(f"[CommandRunner] CRITICAL INITIALIZATION ERROR: {error_details}")

    ccr_tab = Tab(name="Command Runner", icon="bookmark")
    ccr_ui_elements = create_command_runner_ui(ccr_tab)
    ccr_tab.render()

    bot.loop.create_task(ccr_main_initializer(ccr_ui_elements))

    ccr_log_to_file("AutoCommander script started", "INFO", debug_mode=True, important=True)

    # Bot command for listing command configurations
    @bot.command(name="ccr", aliases=["crr"], usage="[p]ccr <help|list|start|stop|edit>")
    async def ccr_handler(ctx, *, args: str = ""):
        if not hasattr(bot, '_command_runner_manager'):
            await ctx.send("Command Runner Manager is not ready. Please reload scripts.", delete_after=10)
            return
        
        manager = bot._command_runner_manager
        await asyncio.sleep(.3)
        await ctx.message.delete()
        parts = args.strip().split()
        subcommand = parts[0].lower() if parts else "help"

        if subcommand == "list":
            current_time = time.time()
            status = "🟢 RUNNING" if manager.running else "🔴 STOPPED"
            
            output_message = f"**Command Runner Status: {status}**\n"

            channels_data = manager.channels_cfg.get("channels", {})
            if not channels_data:
                output_message += "\n📋 No channels are configured."
                await ctx.send(output_message, delete_after=60)
                return

            # Pre-cache channel objects 
            channel_cache = {}
            for cid in channels_data.keys():
                try:
                    channel_obj = bot.get_channel(int(cid))
                    channel_cache[cid] = f"`#{channel_obj.name}`" if channel_obj else "`<Channel not found>`"
                except:
                    channel_cache[cid] = "`<Invalid ID>`"

            async def send_chunk(content):
                if content.strip():
                    await ctx.send(content, delete_after=60)

            last_used = manager.state.get("last_used", {})
            
            for cid, conf in channels_data.items():
                channel_details_lines = []
                channel_name = channel_cache.get(cid, "`<Unknown>`")
                
                # Calculate next execution time
                earliest_next_run = float('inf')
                custom_commands = conf.get("commands", [])
                enabled_commands = [cmd for cmd in custom_commands if cmd.get("enabled", True)]
                
                for cmd in enabled_commands:
                    # Check if command is within its timer time
                    timer_config = cmd.get("timer", {})
                    if not ccr_is_within_timer(timer_config):
                        continue  # Skip commands that are outside their timer window
                    
                    cmd_key = f"{cid}-{cmd.get('name', '')}"
                    cooldown = cmd.get("cooldown", 600)
                    last_run_time_raw = last_used.get(cmd_key, 0)
                    last_run_time = float(last_run_time_raw) if last_run_time_raw != 0 else 0
                    next_run = current_time if last_run_time == 0 else last_run_time + cooldown
                    if next_run < earliest_next_run:
                        earliest_next_run = next_run
                try:
                    earliest_next_run_float = float(earliest_next_run)
                    next_exec_str = f"**Next execution**: <t:{int(earliest_next_run_float)}:R>" if earliest_next_run_float != float('inf') else "**Next execution**: `N/A (all disabled)`"
                except (ValueError, TypeError):
                    next_exec_str = "**Next execution**: `N/A (invalid time)`"
                
                channel_details_lines.append(f"\n- **Channel**: {channel_name} ({cid})")
                channel_details_lines.append(f"  - **Info**: {next_exec_str}")
                
                # Humanization settings 
                h_conf = conf.get("humanization", {})
                typing_status = "🟢" if h_conf.get("typing", True) else "🔴"
                human_delay_config = h_conf.get("human_delay", {"enabled": True, "min": 5, "max": 45})
                human_delay_status = f"🟢 ({human_delay_config.get('min', 5)}-{human_delay_config.get('max', 45)}s)" if human_delay_config.get("enabled", True) else "🔴"
                
                channel_details_lines.append(f"  - **Humanize**: Typing: {typing_status} | Human_delay: {human_delay_status}")
                channel_details_lines.append("  - **Commands**:")
                
                # List all commands 
                if not custom_commands:
                    channel_details_lines.append("    - No commands configured")
                else:
                    for cmd in custom_commands:
                        cmd_name = cmd.get("name", "Unknown")
                        cmd_type = cmd.get("command_type", "prefix")
                        is_enabled = cmd.get("enabled", True)
                        cooldown = cmd.get("cooldown", 600)
                        
                        status_icon = "🟢" if is_enabled else "🔴"
                        
                        # Format command display
                        if cmd_type == "slash":
                            display_cmd = f"/{cmd_name}"
                        else:
                            cmd_prefix = cmd.get("prefix", "!")
                            display_cmd = f"{cmd_prefix}{cmd_name}"
                        
                        # Calculate cooldown status 
                        cmd_key = f"{cid}-{cmd_name}"
                        if not is_enabled:
                            cooldown_remaining = "Disabled"
                        else:
                            # Check if command is within its timer time
                            timer_config = cmd.get("timer", {})
                            if not ccr_is_within_timer(timer_config):
                                cooldown_remaining = "Outside timer window"
                            else:
                                last_run_time_raw = last_used.get(cmd_key, 0)
                                # Ensure last_run_time is a float 
                                last_run_time = float(last_run_time_raw) if last_run_time_raw != 0 else 0
                                if last_run_time == 0:
                                    cooldown_remaining = "Ready"
                                else:
                                    next_run = last_run_time + cooldown
                                    try:
                                        next_run_int = int(float(next_run))
                                        cooldown_remaining = "Ready" if next_run <= current_time else f"<t:{next_run_int}:R>"
                                    except (ValueError, TypeError):
                                        cooldown_remaining = "Invalid time"
                        
                        # Get bot name for display
                        bot_name = cmd.get("bot_name", "")
                        bot_id = cmd.get("bot_id", "")
                        bot_display = bot_name if bot_name else f"ID: {bot_id}"
                        
                        # Display cooldown in original format if available
                        cooldown_display = cmd.get("cooldown_display", f"{cooldown}s")
                        
                        cmd_info = f"{status_icon} `{display_cmd}` ({cmd_type}) - Bot: {bot_display}: `{cooldown_display}` | {cooldown_remaining}"
                        
                        # Add args if present
                        args = cmd.get("args", "")
                        if args:
                            cmd_info += f" | Args: `{args}`"
                        
                        # Add timer info if configured
                        timer = cmd.get("timer", {})
                        if timer.get("enabled") and timer.get("start_time") and timer.get("end_time"):
                            start_time = timer.get("start_time")
                            end_time = timer.get("end_time")
                            days = timer.get("days", [])
                            timer_info = f"{start_time}-{end_time}"
                            if days:
                                timer_info += f" ({', '.join(days)})"
                            cmd_info += f" | Timer: {timer_info}"
                        
                        channel_details_lines.append(f"    - {cmd_info}")

                channel_block = "\n".join(channel_details_lines)
                if len(output_message) + len(channel_block) > 1900: 
                    await send_chunk(output_message)
                    output_message = channel_block.lstrip()
                else:
                    output_message += channel_block

            await send_chunk(output_message)
            return

        elif subcommand == "start":
            manager.state["is_running"] = True
            await manager.ccr_save_state()
            await manager.ccr_start()
            await ctx.send("🟢 Command Runner started.", delete_after=10)
            return
        
        elif subcommand == "stop":
            manager.state["is_running"] = False
            await manager.ccr_save_state()
            await manager.ccr_stop()
            await ctx.send("🔴 Command Runner stopped.", delete_after=10)
            return
        
        elif subcommand == "debug":
            # Toggle debug mode
            try:
                current_debug = manager.state.get("debug_mode", False)
                new_debug = not current_debug
                manager.state["debug_mode"] = new_debug
                await manager.ccr_save_state()
                
                status = "enabled" if new_debug else "disabled"
                await ctx.send(f"Debug mode {status}.", delete_after=10)
                return
            except Exception as e:
                await ctx.send(f"❌ Error toggling debug mode: {str(e)}", delete_after=10)
                return
        
        elif subcommand == "edit":
            # Interactive command editor
            if len(parts) < 2:
                await ctx.send("Usage: `[p]ccr edit <channel_id>` - Opens interactive editor for that channel's commands.", delete_after=15)
                return
            
            try:
                target_channel_id = int(parts[1])
            except ValueError:
                await ctx.send("❌ Invalid channel ID. Please provide a valid channel ID.", delete_after=10)
                return
            
            if str(target_channel_id) not in manager.channels_cfg["channels"]:
                await ctx.send(f"❌ Channel <#{target_channel_id}> is not configured in Command Runner.", delete_after=10)
                return
            
            channel_config = manager.channels_cfg["channels"][str(target_channel_id)]
            commands = channel_config.get("commands", [])
            
            if not commands:
                await ctx.send(f"📋 No commands configured for <#{target_channel_id}>.", delete_after=10)
                return
            
            # Check if this is an action on a specific command
            if len(parts) >= 3:
                try:
                    cmd_index = int(parts[2]) - 1  # Convert to 0-based index
                    if cmd_index < 0 or cmd_index >= len(commands):
                        await ctx.send(f"❌ Invalid command number. Use 1-{len(commands)}.", delete_after=10)
                        return
                except ValueError:
                    await ctx.send("❌ Invalid command number.", delete_after=10)
                    return
                
                if len(parts) < 4:
                    await ctx.send("❌ Missing action. Use: toggle, cooldown, args, or delete.", delete_after=10)
                    return
                
                action = parts[3].lower()
                target_cmd = commands[cmd_index]
                cmd_name = target_cmd.get("name", "")
                
                if action == "toggle":
                    # Toggle command enabled/disabled
                    current_status = target_cmd.get("enabled", True)
                    preserved_slash_type = target_cmd.get("slash_type")
                    preserved_execution_type = target_cmd.get("execution_type")
                    target_cmd["enabled"] = not current_status
                    if preserved_slash_type:
                        target_cmd["slash_type"] = preserved_slash_type
                    if preserved_execution_type:
                        target_cmd["execution_type"] = preserved_execution_type
                    
                    new_status = "enabled" if target_cmd["enabled"] else "disabled"
                    await manager.ccr_save_channels()
                    manager.ccr_trigger_reschedule()
                    await manager.ccr_connect_and_populate_ui()
                    await ctx.send(f"✅ Command `{cmd_name}` has been {new_status}.", delete_after=10)
                    return
                
                elif action == "cooldown":
                    # Change command cooldown
                    if len(parts) < 5:
                        await ctx.send("❌ Missing cooldown value. Usage: `[p]ccr edit <channel_id> <num> cooldown <seconds>`", delete_after=10)
                        return
                    
                    cooldown_input = parts[4]
                    new_cooldown = ccr_parse_time_to_seconds(cooldown_input)
                    if new_cooldown is None or new_cooldown < 1:
                        await ctx.send("❌ Invalid cooldown format. Use: 30s, 5m, 2h, 1d, 1w or just seconds.", delete_after=10)
                        return
                    
                    old_cooldown = target_cmd.get("cooldown", 600)
                    preserved_slash_type = target_cmd.get("slash_type")
                    preserved_execution_type = target_cmd.get("execution_type")
                    target_cmd["cooldown"] = new_cooldown
                    target_cmd["cooldown_display"] = cooldown_input
                    if preserved_slash_type:
                        target_cmd["slash_type"] = preserved_slash_type
                    if preserved_execution_type:
                        target_cmd["execution_type"] = preserved_execution_type
                    
                    # Check if command should execute immediately due to reduced cooldown
                    if new_cooldown < old_cooldown and target_cmd.get("enabled", True):
                        cmd_key = f"{target_channel_id}-{cmd_name}"
                        last_used = manager.state.get("last_used", {})
                        last_run_time_raw = last_used.get(cmd_key, 0)
                        # Ensure last_run_time is a float
                        last_run_time = float(last_run_time_raw) if last_run_time_raw != 0 else 0
                        
                        # If enough time has passed for the new cooldown, reset last_used to trigger immediate execution
                        if last_run_time > 0 and (time.time() - last_run_time) >= new_cooldown:
                            last_used[cmd_key] = time.time() - new_cooldown
                            manager.state["last_used"] = last_used
                            await manager.ccr_save_state()
                            manager.ccr_trigger_reschedule()
                    
                    await manager.ccr_save_channels()
                    await manager.ccr_connect_and_populate_ui()
                    await ctx.send(f"✅ Command `{cmd_name}` cooldown changed to {new_cooldown} seconds.", delete_after=10)
                    return
                
                elif action == "args":
                    preserved_slash_type = target_cmd.get("slash_type")
                    preserved_execution_type = target_cmd.get("execution_type")
                    
                    if len(parts) < 5:
                        # Clear arguments if no value provided
                        target_cmd["args"] = ""
                        if preserved_slash_type:
                            target_cmd["slash_type"] = preserved_slash_type
                        if preserved_execution_type:
                            target_cmd["execution_type"] = preserved_execution_type
                            
                        await manager.ccr_save_channels()
                        await manager.ccr_connect_and_populate_ui()
                        await ctx.send(f"✅ Command `{cmd_name}` arguments cleared.", delete_after=10)
                        return
                    
                    # Join all remaining parts as arguments
                    new_args = " ".join(parts[4:])
                    target_cmd["args"] = new_args
                    if preserved_slash_type:
                        target_cmd["slash_type"] = preserved_slash_type
                    if preserved_execution_type:
                        target_cmd["execution_type"] = preserved_execution_type
                    await manager.ccr_save_channels()
                    await manager.ccr_connect_and_populate_ui()
                    await ctx.send(f"✅ Command `{cmd_name}` arguments updated to: `{new_args}`", delete_after=10)
                    return
                
                elif action == "delete":
                    # Delete command
                    cmd_key = f"{target_channel_id}-{cmd_name}"
                    if "last_used" in manager.state and cmd_key in manager.state["last_used"]:
                        del manager.state["last_used"][cmd_key]
                        await manager.ccr_save_state()
                    
                    if 0 <= cmd_index < len(commands):
                        commands.pop(cmd_index)
                        await manager.ccr_save_channels()
                        await manager.ccr_connect_and_populate_ui()
                        await ctx.send(f"✅ Command `{cmd_name}` has been deleted.", delete_after=10)
                    else:
                        await ctx.send("❌ Invalid command index.", delete_after=10)
                    return
                
                elif action == "type":
                    # Change command type between prefix and slash
                    if len(parts) < 5:
                        await ctx.send("❌ Missing command type. Usage: `[p]ccr edit <channel_id> <num> type <prefix|slash>`", delete_after=10)
                        return
                    
                    new_type = parts[4].lower()
                    if new_type not in ["prefix", "slash"]:
                        await ctx.send("❌ Invalid command type. Use: prefix or slash.", delete_after=10)
                        return
                    
                    old_type = target_cmd.get("command_type", "prefix")
                    preserved_slash_type = target_cmd.get("slash_type")
                    preserved_execution_type = target_cmd.get("execution_type")
                    
                    target_cmd["command_type"] = new_type
                    
                    # If changing to prefix and no prefix is set, use default
                    if new_type == "prefix" and not target_cmd.get("prefix"):
                        target_cmd["prefix"] = "!"
                    
                    if preserved_slash_type:
                        target_cmd["slash_type"] = preserved_slash_type
                    if preserved_execution_type:
                        target_cmd["execution_type"] = preserved_execution_type
                    
                    await manager.ccr_save_channels()
                    await manager.ccr_connect_and_populate_ui()
                    await ctx.send(f"✅ Command `{cmd_name}` type changed from `{old_type}` to `{new_type}`.", delete_after=10)
                    return
                
                elif action == "timer":
                    # Configure command timer
                    if len(parts) < 5:
                        await ctx.send("❌ Missing timer action. Usage: `[p]ccr edit <channel_id> <num> timer <set|clear|toggle>`", delete_after=10)
                        return
                    
                    timer_action = parts[4].lower()
                    
                    if timer_action == "clear":
                        # Clear timer configuration
                        preserved_slash_type = target_cmd.get("slash_type")
                        preserved_execution_type = target_cmd.get("execution_type")
                        
                        if "timer" in target_cmd:
                            del target_cmd["timer"]
                        
                        if preserved_slash_type:
                            target_cmd["slash_type"] = preserved_slash_type
                        if preserved_execution_type:
                            target_cmd["execution_type"] = preserved_execution_type
                        await manager.ccr_save_channels()
                        manager.ccr_trigger_reschedule()
                        await manager.ccr_connect_and_populate_ui()
                        await ctx.send(f"✅ Timer cleared for command `{cmd_name}`.", delete_after=10)
                        return
                    
                    elif timer_action == "toggle":
                        # Toggle timer enabled/disabled
                        timer = target_cmd.get("timer", {})
                        if not timer.get("start_time") or not timer.get("end_time"):
                            await ctx.send("❌ No timer configured for this command. Use 'set' first.", delete_after=10)
                            return
                        
                        preserved_slash_type = target_cmd.get("slash_type")
                        preserved_execution_type = target_cmd.get("execution_type")
                        
                        current_enabled = timer.get("enabled", True)
                        timer["enabled"] = not current_enabled
                        target_cmd["timer"] = timer
                        
                        if preserved_slash_type:
                            target_cmd["slash_type"] = preserved_slash_type
                        if preserved_execution_type:
                            target_cmd["execution_type"] = preserved_execution_type
                        
                        status = "enabled" if timer["enabled"] else "disabled"
                        await manager.ccr_save_channels()
                        manager.ccr_trigger_reschedule()
                        await manager.ccr_connect_and_populate_ui()
                        await ctx.send(f"✅ Timer {status} for command `{cmd_name}`.", delete_after=10)
                        return
                    
                    elif timer_action == "set":
                        # Set timer configuration
                        if len(parts) < 7:
                            await ctx.send("❌ Missing timer parameters. Usage: `[p]ccr edit <channel_id> <num> timer set <start_time> <end_time> [days...]`\nExample: `[p]ccr edit 123 1 timer set 09:00 17:00 monday friday`", delete_after=15)
                            return
                        
                        start_time = parts[5]
                        end_time = parts[6]
                        days = [day.lower() for day in parts[7:]] if len(parts) > 7 else []
                        
                        # Validate time format
                        time_pattern = r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$'
                        if not re.match(time_pattern, start_time) or not re.match(time_pattern, end_time):
                            await ctx.send("❌ Invalid time format. Use HH:MM format (e.g., 09:00, 17:30).", delete_after=10)
                            return
                        
                        # Validate days if provided
                        valid_days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                        if days and not all(day in valid_days for day in days):
                            await ctx.send(f"❌ Invalid day(s). Valid days: {', '.join(valid_days)}", delete_after=10)
                            return
                        
                        # Set timer configuration
                        preserved_slash_type = target_cmd.get("slash_type")
                        preserved_execution_type = target_cmd.get("execution_type")
                        
                        target_cmd["timer"] = {
                            "enabled": True,
                            "start_time": start_time,
                            "end_time": end_time,
                            "days": days
                        }
                        
                        if preserved_slash_type:
                            target_cmd["slash_type"] = preserved_slash_type
                        if preserved_execution_type:
                            target_cmd["execution_type"] = preserved_execution_type
                        
                        await manager.ccr_save_channels()
                        manager.ccr_trigger_reschedule()
                        await manager.ccr_connect_and_populate_ui()
                        
                        days_str = f" on {', '.join(days)}" if days else " (all days)"
                        await ctx.send(f"✅ Timer set for command `{cmd_name}`: {start_time}-{end_time}{days_str}.", delete_after=10)
                        return
                    
                    else:
                        await ctx.send("❌ Invalid timer action. Use: set, clear, or toggle.", delete_after=10)
                        return
                
                else:
                    await ctx.send("❌ Invalid action. Use: toggle, cooldown, args, delete, type, or timer.", delete_after=10)
                    return
            
            # Display commands with numbers for selection
            cmd_list = "**Commands in** <#{}>:\n\n".format(target_channel_id)
            for i, cmd in enumerate(commands, 1):
                status = "🟢" if cmd.get("enabled", True) else "🔴"
                cmd_type = cmd.get("command_type", "prefix")
                cmd_name = cmd.get("name", "")
                cooldown = cmd.get("cooldown", 600)
                args = cmd.get("args", "")
                
                if cmd_type == "slash":
                    display_name = f"/{cmd_name}"
                else:
                    prefix = cmd.get("prefix", "!")
                    display_name = f"{prefix}{cmd_name}"
                
                cmd_list += f"{i}. {status} `{display_name}` ({cmd_type}) - {cooldown}s"
                if args:
                    cmd_list += f" | Args: `{args}`"
                cmd_list += "\n"
            
            cmd_list += "\n**Actions:**\n"
            cmd_list += "• `[p]ccr edit {0} <num> toggle` - Enable/disable command\n".format(target_channel_id)
            cmd_list += "• `[p]ccr edit {0} <num> cooldown <time>` - Change cooldown (e.g., 30s, 5m, 2h, 1d)\n".format(target_channel_id)
            cmd_list += "• `[p]ccr edit {0} <num> args <arguments>` - Change arguments\n".format(target_channel_id)
            cmd_list += "• `[p]ccr edit {0} <num> type <prefix|slash>` - Change command type\n".format(target_channel_id)
            cmd_list += "• `[p]ccr edit {0} <num> timer set <start> <end> [days...]` - Set timer\n".format(target_channel_id)
            cmd_list += "• `[p]ccr edit {0} <num> timer toggle` - Enable/disable timer\n".format(target_channel_id)
            cmd_list += "• `[p]ccr edit {0} <num> timer clear` - Remove timer\n".format(target_channel_id)
            cmd_list += "• `[p]ccr edit {0} <num> delete` - Delete command\n".format(target_channel_id)
            
            await ctx.send(cmd_list, delete_after=120)
            return
        
        else:  # Help command
            help_text = (
                "**Command Runner Help Guide**\n\n"
                "--- **Core Commands** ---\n"
                "- `[p]ccr start` - Starts the command runner process.\n"
                "- `[p]ccr stop` - Stops the command runner process.\n"
                "- `[p]ccr list` - Displays detailed status and command information.\n"
                "- `[p]ccr edit <channel_id>` - Interactive command editor for a specific channel.\n"
                "- `[p]ccr debug` - Toggle debug mode for detailed logging.\n"
                "- `[p]ccr help` - Shows this help message.\n\n"

                "--- **Usage** ---\n"
                "Use the UI to configure channels and commands.\n\n"
                
                "--- **Slash Commands with Arguments** ---\n"
                "Format: key=value separated by spaces. For multi-word values, use quotes:\n"
                "Examples:\n"
                "• duration=2m winners=1 prize=test\n"
                "• duration=10m winners=2 prize=\"Nitro Monthly\"\n"
                "• time=1h reward=\"Discord Premium\" count=5\n\n"
                "**For mentions (users/channels/roles), use their ID:**\n"
                "• target=123456789012345678 amount=1000\n"
                "• user=987654321098765432 role=456789123456789123\n"
                "• channel=789123456789123456 message=\"Hello World\"\n\n"
                
                "--- **Timer Examples** ---\n"
                "Set timer for all days:\n"
                "• `[p]ccr edit 123456 1 timer set 09:00 17:00`\n\n"
                "Set timer for specific days:\n"
                "• `[p]ccr edit 123456 1 timer set 18:00 22:00 monday friday`\n"
                "• `[p]ccr edit 123456 1 timer set 08:30 12:30 saturday sunday`\n\n"
                "Timer management:\n"
                "• `[p]ccr edit 123456 1 timer toggle` - Enable/disable timer\n"
                "• `[p]ccr edit 123456 1 timer clear` - Remove timer completely\n"
            )
            await ctx.send(help_text, delete_after=60)
            return
    
custom_command_runner_script()


