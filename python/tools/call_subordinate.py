from agent import Agent, UserMessage
from python.helpers.tool import Tool, Response
from initialize import initialize_agent
from python.extensions.hist_add_tool_result import _90_save_tool_call_file as save_tool_call_file


class Delegation(Tool):

    async def execute(self, message="", reset="", **kwargs):
        # create subordinate agent using the data object on this agent and set superior agent to his data object
        if (
            self.agent.get_data(Agent.DATA_NAME_SUBORDINATE) is None
            or str(reset).lower().strip() == "true"
        ):
            # initialize default config
            config = initialize_agent()

            # override chat model with subagent model if configured
            if config.subagent_model:
                config.chat_model = config.subagent_model

            # set subordinate prompt profile if provided, if not, keep original
            agent_profile = kwargs.get("profile", kwargs.get("agent_profile", ""))
            if agent_profile:
                config.profile = agent_profile

            # crate agent
            sub = Agent(self.agent.number + 1, config, self.agent.context)
            # register superior/subordinate
            sub.set_data(Agent.DATA_NAME_SUPERIOR, self.agent)
            self.agent.set_data(Agent.DATA_NAME_SUBORDINATE, sub)

        # add user message to subordinate agent
        subordinate: Agent = self.agent.get_data(Agent.DATA_NAME_SUBORDINATE)  # type: ignore
        subordinate.hist_add_user_message(UserMessage(message=message, attachments=[]))

        # Log task delegation details
        sub_model = f"{subordinate.config.chat_model.provider}/{subordinate.config.chat_model.name}"
        self.log.update(
            task=message[:500],
            subordinate_model=sub_model,
            status="running",
        )

        # run subordinate monologue
        result = await subordinate.monologue()

        # Log task completion with result summary
        result_preview = result[:500] if result else "(empty)"
        self.log.update(
            status="completed",
            result=result_preview,
        )

        # seal the subordinate's current topic so messages move to `topics` for compression
        subordinate.history.new_topic()

        # hint to use includes for long responses
        additional = None
        if len(result) >= save_tool_call_file.LEN_MIN:
            hint = self.agent.read_prompt("fw.hint.call_sub.md")
            if hint:
                additional = {"hint": hint}

        # result
        return Response(message=result, break_loop=False, additional=additional)

    def get_log_object(self):
        # Determine subordinate model
        sub_model = ""
        if self.agent.config.subagent_model:
            sub_model = f"{self.agent.config.subagent_model.provider}/{self.agent.config.subagent_model.name}"
        else:
            sub_model = f"{self.agent.config.chat_model.provider}/{self.agent.config.chat_model.name}"
        kvps = dict(self.args) if self.args else {}
        kvps["subordinate_model"] = sub_model
        return self.agent.context.log.log(
            type="subagent",
            heading=f"icon://communication {self.agent.agent_name}: Calling Subordinate Agent",
            content="",
            kvps=kvps,
        )

