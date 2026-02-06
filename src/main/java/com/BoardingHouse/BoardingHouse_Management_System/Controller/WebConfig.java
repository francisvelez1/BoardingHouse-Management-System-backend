package com.BoardingHouse.BoardingHouse_Management_System.Controller;


import java.util.Arrays;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/*  This configuration allows you to connect to the frontend and backend using the local api.
    All origins are allowed to connect to the backend, but you can change it to your frontend URL in deployment. 
     For example, if your frontend is hosted at http://myfrontend.com, you can set the allowed origins to that URL.
     In production, you might want to allow all origins or specify a different set of allowed origins based on your deployment needs.

    Note that this solly based on the pattern recognitions that all files that specified in the controller are under the /api/ path, so it will only allow CORS for those endpoints. 
    You can adjust the path pattern as needed.
*/
@Configuration
public class WebConfig {
    @Bean
    public WebMvcConfigurer corsConfigurer() {
        return new WebMvcConfigurer() {
            //@SuppressWarnings("null")    
            @Bean
        public CorsConfigurationSource corsConfigurationSource() {
            CorsConfiguration configuration = new CorsConfiguration();
            // this origins freely connect to the frontend localhost:3000, you can change it to your frontend URL in deployment
            configuration.setAllowedOrigins(Arrays.asList("http://localhost:3000"));
            configuration.setAllowedMethods(Arrays.asList("GET", "POST", "PUT", "DELETE"));
            configuration.setAllowedHeaders(Arrays.asList("*"));
            configuration.setAllowCredentials(true);

            // Use this configuration to allow all origins (for production)
           // configuration.setAllowedOriginPatterns(Arrays.asList("http://localhost:*"));


            UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
            source.registerCorsConfiguration("/api/**", configuration);
            return source;
                }
        };
    }
}
