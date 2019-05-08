import abc
import shlex
import inspect
from discord.ext import commands
from discord.ext.commands import converter as converters

__all__ = [
    "OptionalArgument", "RequiredArgument", "ArgumentConverter",
    "InvalidArgumentValueError", "UnknownArgumentError"
]


class Argument(abc.ABC):
    """ An ABC for passable arguments. """

    def __init__(self, converter, doc="", default=None):
        """ Initializes the Argument.

        Parameters
        ----------
        converter:
            The converter to use. This follows the requirements of a
            :class:`discord.ext.commands.Converter`.
        doc: str
            An optional documentation string. Will be displayed in the help
            command.
        default: object
            The default value to use for OptionalArguments. If this is None,
            the argument won't be included in the results.
        """
        self.converter = converter
        self.doc = doc
        self.default = default


class OptionalArgument(Argument):
    """ An optional argument. """
    ...


class RequiredArgument(Argument):
    """ A required argument. """
    ...


class ArgumentConverter(commands.Converter):
    """ Provides support for arbitrarily ordered named arguments in commands.

    By using this converter, users can supply named arguments in arbitrary order
    to a command by passing a series of key=value-pairs, separated by spaces.
    For example: `!quiz pokemon turns=2 images=true voice_channel=voice-quiz`.

    To use it, create an instance of this class and pass to it required and
    optional parameters. Then create a single keyword-only argument and annotate
    its type using the instance of this class.

    .. code-block: python3

        param_converter = ArgumentConverter(
            turns = RequiredArgument(
                int,
                doc="The number of turns this quiz has.",
                default=10
            ),
            images = OptionalArgument(
                bool,
                doc="(Dis-)allow image questions.",
                default=True
            ),
            voice_channel = OptionalArgument(
                discord.VoiceChannel
            )
        )

        # ...

        @bot.command()
        async def quiz(ctx, name:str, *, params:param_converter=param_converter.defaults()):
            await ctx.send("Turns: {0}".format(params['turns']))
        
        @quiz.error
        async def quiz_error(ctx, error):
            if isinstance(error, InvalidArgumentValueError):
                await ctx.send(
                    "Invalid argument value for parameter {0}".format(error.name)
                )
            elif isinstance(error, UnknownArgumentError):
                await ctx.send(
                    "Unknown argument {0}".format(error.name)
                )

    By using `param_converter.defaults()`, the `params` dict is initialized with
    the default values supplied.

    In case an error is encountered while parsing the arguments, an
    :class:`InvalidArgumentError` or :class:`UnknownArgumentError` is raised.
    Both are subclasses of :class:`discord.ext.commands.BadArgument`.
    """

    def __init__(self, **arguments):
        """ Initializes the argument parser.

        Parameters
        ----------
        arguments: [Argument]
            A list of :class:`Argument`s.
        """
        self.arguments = arguments
    
    def _convert_to_bool(self, value):
        """ Converts a string value to bool.

        Raises :class:`discord.ext.commands.ConversionError` if the conversion
        fails.
        """
        lowered = value.lower()
        if lowered in ("ja", "yes", "y", "true", "t", "1", "enable", "on"):
            return True
        elif lowered in ("nein", "no", "false", "f", "0", "disable", "off"):
            return False
        raise commands.ConversionError(value, None)
    
    async def _convert_value(self, ctx, converter, value):
        """ Converts the given value with the supplied converter.

        Raises a :class:`discord.commands.ConversionError` if the conversion fails.
        """
        # This essentialy is a rip-off of the _actual_conversion() method in
        # discord.py's ext/commands/core.py file
        if converter is bool:
            return _convert_to_bool(value)
        
        try:
            module = converter.__module__
        except ValueError:
            ...
        else:
            if module is not None and (module.startswith("discord.")
                    and not module.endswith("converter")):
                converter = getattr(converters, converter.__name__  + "Converter")
        
        try:
            if inspect.isclass(converter):
                if issubclass(converter, commands.Converter):
                    instance = converter()
                    ret = await instance.convert(ctx, value)
                    return ret
                method = getattr(converter, "convert", None)
                if method is not None and inspect.ismethod(method):
                    ret = await method(ctx, value)
            elif isinstance(converter, commands.Converter):
                ret = await converter.convert(ctx, value)
                return ret
        except Exception as e:
            raise commands.ConversionError(converter, e) from e

        try:
            return converter(value)
        except Exception as e:
            raise commands.ConversionError(converter, e) from e
    
    async def convert(self, ctx, argstr):
        converted = {}

        for raw_arg in shlex.split(argstr or ""):
            if "=" not in raw_arg:
                continue
            name, *values = raw_arg.split("=")
            value = "=".join(values)

            argument = self.arguments.get(name.lower())
            if not argument:
                raise UnknownArgumentError(name)

            try:
                converted_value = await self._convert_value(
                    ctx,
                    argument.converter,
                    value
                )
                converted[name] = converted_value
            except commands.ConversionError:
                raise InvalidArgumentValueError(name, value)
            except Exception as e:
                raise commands.ConversionError(self, e) from e
        
        for name, argument in self.arguments.items():
            if isinstance(argument, RequiredArgument) and name not in converted:
                param = inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY)
                raise commands.MissingRequiredArgument(param)

            if argument.default is not None and name not in converted:
                converted[name] = argument.default

        return converted
    
    def defaults(self):
        """ Returns the arguments default values. """
        default_arguments = {}
        for name, argument in self.arguments.items():
            if argument.default is not None:
                default_arguments[name] = argument.default
        return default_arguments


class InvalidArgumentValueError(commands.BadArgument):
    """ Exception raised when an argument cannot be converted with a
    converter. """

    def __init__(self, name, value):
        super().__init__(
            "Invalid argument value passed for {0}: {1}".format(name, value)
        )
        self.name = name
        self.value = value


class UnknownArgumentError(commands.BadArgument):
    """ Exception raised when an unknown argument is passed. """

    def __init__(self, name):
        super().__init__("Unknown named argument {0}".format(name))
        self.name = name