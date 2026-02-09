package com.BoardingHouse.BoardingHouse_Management_System.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.config.Customizer;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    private final WebConfig webConfig;

    // Injecting WebConfig to access the CORS configuration source
    public SecurityConfig(WebConfig webConfig) {
        this.webConfig = webConfig;
    }

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(); // Used by AuthenticationService to hash/match passwords
    }

    @Bean
    public AuthenticationManager authenticationManager(
            AuthenticationConfiguration authConfig) throws Exception {
        return authConfig.getAuthenticationManager(); // Required for the AuthenticationService to validate users
    }

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {

        http
            // Enable CORS using the source defined in WebConfig
            .cors(cors -> cors.configurationSource(webConfig.corsConfigurationSource()))
            
            // Disable CSRF for REST API compatibility
            .csrf(csrf -> csrf.disable())

            .authorizeHttpRequests(auth -> auth
                // Permitting access to the API authentication endpoints and standard pages
                .requestMatchers("/api/auth/**", "/login", "/register", "/css/**", "/js/**").permitAll()
                .anyRequest().authenticated()
            )

            // Keeping formLogin for traditional session-based access if needed
            .formLogin(form -> form
                .loginPage("/login")
                .defaultSuccessUrl("/dashboard", true)
                .permitAll()
            )

            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
            )

            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}