{# Jinja2 template for generating a MapStruct mapper interface #}
{# Variables:
    package_name:           The Java package for the mapper class.
    original:               The original domain class being refactored
        original.name:      The simple name of the original domain class.
        original.full_name: The fully qualified name of the original domain class.
    dto:                    The DTO class of the original domain class.
        dto.name:           The simple name of the DTO class.
        dto.full_name:      The fully qualified name of the DTO class.
    mapper:                 The name of the generated mapper class.
        mapper.name:        The simple name of the mapper class.
#}
package {{ package_name }}.generated.server;

import org.mapstruct.Mapper;
import org.mapstruct.factory.Mappers;
import {{ dto.full_name }};
import {{ original.full_name }};

/**
 * Auto-generated MapStruct mapper for converting between
 * {@link {{ original.name }}} and {@link {{ dto.name }}}.
 */
@Mapper(componentModel = "default") 
public interface {{ mapper.name }} {
    /**
     * Singleton instance of this mapper. Use this to access mapping methods.
     */
    {{ mapper.name }} INSTANCE = Mappers.getMapper({{ mapper.name }}.class);

    /**
     * Maps from {@link {{ dto.name }}} to {@link {{ original.name }}}.
     *
     * @param dto The source DTO object.
     * @return The mapped {@link {{ original.name }}} object.
     */
    {{ original.name }} fromDTO({{ dto.name }} dto);

    /**
     * Maps from {@link {{ original.name }}} to {@link {{ dto.name }}}.
     *
     * @param original The source of the Original object.
     * @return The mapped {@link {{ dto.name }}} object.
     */
    {{ dto.name }} toDTO({{ original.name }} domain);

}